# api/app/llm_service.py
from __future__ import annotations

import json
import logging
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from .models import LLMConfig, ChatMessage, User
from .chat_tools import AVAILABLE_TOOLS, execute_tool_by_name, get_intelligent_system_prompt

log = logging.getLogger(__name__)

# ─── Provider Registry ────────────────────────────────────────────────────────
# To add a provider: one entry here, no other code changes needed.
# api_compat="openai"     → OpenAI SDK with optional base_url override
# api_compat="anthropic"  → Anthropic SDK with optional base_url override
#                           (use for Anthropic-compatible proxies like z.ai)
PROVIDER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "openai": {
        "api_compat": "openai",
        "default_base_url": None,
        "display": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "anthropic": {
        "api_compat": "anthropic",
        "default_base_url": None,
        "display": "Anthropic (Claude)",
        "models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    },
    "zhipu": {
        # GLM restricts tool calling on the OpenAI-compat API.
        # z.ai exposes an Anthropic-compat proxy that supports full tool use.
        "api_compat": "anthropic",
        "default_base_url": "https://api.z.ai/api/anthropic",
        "display": "Zhipu AI (GLM) via z.ai",
        "models": ["glm-5.2", "glm-4", "glm-4-plus", "glm-4-flash"],
    },
}

class LLMService:
    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config
        self.client = self._create_client()
    
    def _create_client(self):
        """Create the appropriate LLM client based on the provider registry"""
        try:
            api_key = self.config.get_api_key()
        except Exception as e:
            log.error(f"[llm] Failed to decrypt API key for config {self.config.id}: {e}")
            raise ValueError(f"Failed to decrypt API key: {str(e)}")

        if not api_key:
            raise ValueError("No API key found in LLM config")

        provider = self.config.provider.lower()
        meta = PROVIDER_REGISTRY.get(provider)
        if not meta:
            raise ValueError(f"Unsupported LLM provider: {provider}. Valid: {list(PROVIDER_REGISTRY)}")

        log.info(f"[llm] Using API key starting with: {api_key[:8]}... for provider {provider}")

        if meta["api_compat"] == "openai":
            try:
                import openai
            except ImportError:
                raise RuntimeError("OpenAI package not installed. Run: pip install openai")
            base_url = getattr(self.config, "base_url", None) or meta["default_base_url"]
            kwargs: Dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            return openai.OpenAI(**kwargs)

        elif meta["api_compat"] == "anthropic":
            try:
                import anthropic
            except ImportError:
                raise RuntimeError("Anthropic package not installed. Run: pip install anthropic")
            base_url = getattr(self.config, "base_url", None) or meta["default_base_url"]
            kwargs: Dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            return anthropic.Anthropic(**kwargs)

        else:
            raise ValueError(f"Unknown api_compat value '{meta['api_compat']}' for provider {provider}")
    
    def generate_response(
        self, 
        conversation_messages: List[ChatMessage], 
        system_prompt: Optional[str], 
        client_id: str
    ) -> Dict[str, Any]:
        """Generate a response from the LLM with intelligent context"""
        try:
            log.info(f"[llm] Generating response using config: {self.config.name} (ID: {self.config.id})")
            
            # Use intelligent system prompt if no custom system prompt provided
            if not system_prompt:
                system_prompt = get_intelligent_system_prompt(client_id, conversation_messages)
            
            meta = PROVIDER_REGISTRY.get(self.config.provider.lower(), {})
            api_compat = meta.get("api_compat", "openai")
            if api_compat == "openai":
                return self._generate_openai_response(conversation_messages, system_prompt, client_id)
            elif api_compat == "anthropic":
                return self._generate_anthropic_response(conversation_messages, system_prompt, client_id)
            else:
                raise ValueError(f"Unsupported api_compat '{api_compat}' for provider: {self.config.provider}")
        
        except Exception as e:
            log.error(f"[llm] Error generating response: {e}")
            return {
                "content": "I apologize, but I encountered an error while processing your request. Please try again.",
                "error": str(e)
            }
    
    def _generate_openai_response(
        self, 
        conversation_messages: List[ChatMessage], 
        system_prompt: Optional[str], 
        client_id: str
    ) -> Dict[str, Any]:
        """Generate response using OpenAI API"""
        messages = []
        
        # Add system prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Convert conversation to OpenAI format with proper tool handling
        i = 0
        while i < len(conversation_messages):
            msg = conversation_messages[i]
            
            if msg.role == "user":
                messages.append({
                    "role": "user",
                    "content": msg.content
                })
            elif msg.role == "assistant":
                # Check if this assistant message has tool calls
                if msg.tool_name and msg.tool_args:
                    # This is an assistant message with tool calls
                    try:
                        tool_args = json.loads(msg.tool_args) if isinstance(msg.tool_args, str) else msg.tool_args
                    except json.JSONDecodeError:
                        tool_args = {}
                    
                    messages.append({
                        "role": "assistant", 
                        "content": msg.content,
                        "tool_calls": [{
                            "id": f"call_{str(msg.id)[:32]}",  # Truncate to max 40 chars (call_ + 32 chars)
                            "type": "function",
                            "function": {
                                "name": msg.tool_name,
                                "arguments": json.dumps(tool_args)
                            }
                        }]
                    })
                    
                    # Look for the corresponding tool response
                    if i + 1 < len(conversation_messages) and conversation_messages[i + 1].role == "tool":
                        tool_msg = conversation_messages[i + 1]
                        messages.append({
                            "role": "tool",
                            "content": tool_msg.content,
                            "tool_call_id": f"call_{str(msg.id)[:32]}"  # Same truncated ID
                        })
                        i += 1  # Skip the tool message since we processed it
                else:
                    # Regular assistant message without tools
                    messages.append({
                        "role": "assistant",
                        "content": msg.content
                    })
            elif msg.role == "system":
                # Skip system messages that aren't the initial system prompt
                # as they're usually status messages
                pass
            # Note: We handle tool messages above with their corresponding assistant messages
            
            i += 1
        
        # Prepare enhanced function calling with all available tools
        functions = []
        for tool_name, tool_def in AVAILABLE_TOOLS.items():
            functions.append({
                "type": "function",
                "function": {
                    "name": tool_def["name"],
                    "description": tool_def["description"],
                    "parameters": tool_def["parameters"]
                }
            })
        
        # Retry logic for OpenAI API calls (handles transient 500 errors)
        max_retries = 3
        retry_delay = 1  # seconds

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=self.config.temperature,
                    tools=functions,
                    tool_choice="auto"
                )
                break  # Success, exit retry loop
            except Exception as e:
                log.error(f"[llm] OpenAI API call failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    log.info(f"[llm] Retrying in {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    log.error(f"[llm] All {max_retries} retry attempts failed")
                    raise e
        
        message = response.choices[0].message
        
        # Check if function was called
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            try:
                function_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                function_args = {}
            
            return {
                "content": message.content or f"I'll execute the {tool_call.function.name} tool.",
                "tool_name": tool_call.function.name,
                "tool_args": json.dumps(function_args)
            }
        
        return {
            "content": message.content or "I apologize, but I couldn't generate a response."
        }
    
    def _generate_anthropic_response(
        self,
        conversation_messages: List[ChatMessage],
        system_prompt: Optional[str],
        client_id: str
    ) -> Dict[str, Any]:
        """Generate response using Anthropic API (or Anthropic-compatible proxy like z.ai)"""
        messages = []

        # Reconstruct conversation in proper Anthropic format, preserving tool call history.
        # Without this, the model never sees previous command results and gets stuck repeating
        # the startup message instead of continuing execution.
        i = 0
        while i < len(conversation_messages):
            msg = conversation_messages[i]

            if msg.role == "user":
                messages.append({"role": "user", "content": msg.content})

            elif msg.role == "assistant":
                if msg.tool_name and msg.tool_args:
                    # Assistant made a tool call — build Anthropic tool_use content block
                    tool_id = f"call_{str(msg.id)[:32]}"
                    try:
                        tool_input = json.loads(msg.tool_args) if isinstance(msg.tool_args, str) else msg.tool_args
                    except json.JSONDecodeError:
                        tool_input = {}

                    content_blocks: List[Dict[str, Any]] = []
                    if msg.content:
                        content_blocks.append({"type": "text", "text": msg.content})
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tool_id,
                        "name": msg.tool_name,
                        "input": tool_input
                    })
                    messages.append({"role": "assistant", "content": content_blocks})

                    # Pair with the following tool result message
                    if i + 1 < len(conversation_messages) and conversation_messages[i + 1].role == "tool":
                        tool_msg = conversation_messages[i + 1]
                        messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": tool_msg.content or ""
                            }]
                        })
                        i += 1  # consumed the tool message
                else:
                    messages.append({"role": "assistant", "content": msg.content})
            # skip "system" and orphan "tool" messages

            i += 1

        tools = []
        for tool_name, tool_def in AVAILABLE_TOOLS.items():
            tools.append({
                "name": tool_def["name"],
                "description": tool_def["description"],
                "input_schema": tool_def["parameters"]
            })

        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=8192,
                temperature=self.config.temperature,
                system=system_prompt or "You are a helpful AI assistant for Windows system administration with access to powerful PowerShell tools.",
                messages=messages,
                tools=tools
            )
        except Exception as e:
            log.error(f"[llm] Anthropic API call failed: {e}")
            raise e

        log.info(f"[llm] Anthropic response: stop_reason={response.stop_reason}, "
                 f"blocks={[getattr(b, 'type', '?') for b in response.content]}")

        # Find tool_use block anywhere in content — the model often returns a text block
        # BEFORE the tool_use block, so checking only content[0] misses the tool call.
        tool_block = next(
            (b for b in response.content if getattr(b, "type", None) == "tool_use"),
            None
        )

        if tool_block is not None or response.stop_reason == "tool_use":
            if tool_block is not None:
                text_parts = [
                    b.text for b in response.content
                    if getattr(b, "type", None) == "text" and hasattr(b, "text")
                ]
                return {
                    "content": " ".join(text_parts) if text_parts else f"Executing {tool_block.name}...",
                    "tool_name": tool_block.name,
                    "tool_args": json.dumps(tool_block.input)
                }

        # No tool use — collect all text blocks
        text_parts = [
            b.text for b in response.content
            if hasattr(b, "text") and b.text
        ]
        full_text = "\n".join(text_parts) if text_parts else ""

        # Fallback: GLM via z.ai may not translate its native tool call format
        # to proper Anthropic tool_use blocks — parse it from the text instead.
        if full_text:
            parsed = self._parse_text_based_tool_call(full_text)
            if parsed:
                return {
                    "content": f"Executing {parsed['tool_name']}...",
                    "tool_name": parsed["tool_name"],
                    "tool_args": json.dumps(parsed["args"])
                }

        return {
            "content": full_text or "I couldn't generate a response."
        }

    def _parse_text_based_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse GLM's text-based tool call formats when z.ai doesn't produce proper tool_use blocks."""
        # Format 1: XML key/value pairs — GLM-5.2 via z.ai observed format:
        #   [prefix] tool_name<arg_key>param</arg_key><arg_value>val</arg_value>...
        if "<arg_key>" in text and "<arg_value>" in text:
            for tool_name in AVAILABLE_TOOLS:
                if tool_name in text:
                    pairs = re.findall(
                        r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>",
                        text, re.DOTALL
                    )
                    if pairs:
                        args = {k.strip(): v.strip() for k, v in pairs}
                        log.info(f"[llm] Parsed GLM XML tool call: {tool_name}({list(args.keys())})")
                        return {"tool_name": tool_name, "args": args}

        # Format 2: JSON inside <tool_call> tags — GLM-4 native format:
        #   <tool_call>{"name": "fn", "arguments": {...}}</tool_call>
        tool_call_match = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
        if tool_call_match:
            try:
                call_data = json.loads(tool_call_match.group(1))
                tool_name = call_data.get("name") or call_data.get("function")
                arguments = call_data.get("arguments") or call_data.get("parameters") or {}
                if tool_name and tool_name in AVAILABLE_TOOLS:
                    log.info(f"[llm] Parsed GLM JSON tool call: {tool_name}({list(arguments.keys())})")
                    return {"tool_name": tool_name, "args": arguments}
            except (json.JSONDecodeError, AttributeError):
                pass

        return None
    
    def execute_tool(
        self, 
        tool_name: str, 
        tool_args: str, 
        client_id: str, 
        db: Session, 
        user: User,
        conversation_messages: List[ChatMessage] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute a tool and return the result with intelligent context"""
        try:
            # Parse tool arguments
            if isinstance(tool_args, str):
                try:
                    args_dict = json.loads(tool_args)
                except json.JSONDecodeError:
                    args_dict = {"error": "Invalid JSON in tool arguments"}
            else:
                args_dict = tool_args or {}
            
            log.info(f"[llm] Executing tool {tool_name} with args: {args_dict}")
            
            # Use the enhanced tool execution system with conversation context
            result = execute_tool_by_name(
                tool_name, 
                args_dict, 
                client_id, 
                db, 
                user, 
                conversation_context=conversation_messages or []
            )
            
            if result.get("success"):
                return {
                    "content": result.get("message", "Tool executed successfully"),
                    "execution_details": {
                        "instruction_id": result.get("instruction_id"),
                        "explanation": result.get("explanation"),
                        "safety_assessment": result.get("safety_assessment"),
                        "context_applied": result.get("context_applied", False)
                    }
                }
            else:
                error_msg = result.get("message", "Tool execution failed")
                if result.get("safety_warning"):
                    error_msg = f"⚠️ Safety Warning: {error_msg}"
                
                return {
                    "content": error_msg,
                    "error": result.get("error"),
                    "safety_warning": result.get("safety_warning", False)
                }
        
        except Exception as e:
            log.error(f"[llm] Tool execution error for {tool_name}: {e}")
            return {
                "content": f"Error executing {tool_name}: {str(e)}",
                "error": str(e)
            }


# Utility function for backward compatibility
def get_llm_service(llm_config_id: str, db: Session) -> Optional[LLMService]:
    """Get an LLM service instance for a config ID"""
    config = db.get(LLMConfig, llm_config_id)
    if config and config.is_active:
        return LLMService(config)
    return None