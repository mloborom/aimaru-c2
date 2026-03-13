# api/app/llm_service.py
from __future__ import annotations

import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from .models import LLMConfig, ChatMessage, User
from .chat_tools import AVAILABLE_TOOLS, execute_tool_by_name, get_intelligent_system_prompt

log = logging.getLogger(__name__)

class LLMService:
    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config
        self.client = self._create_client()
    
    def _create_client(self):
        """Create the appropriate LLM client based on provider"""
        # Use the get_api_key() method to properly decrypt the API key
        try:
            api_key = self.config.get_api_key()
        except Exception as e:
            log.error(f"[llm] Failed to decrypt API key for config {self.config.id}: {e}")
            raise ValueError(f"Failed to decrypt API key: {str(e)}")
        
        if not api_key:
            raise ValueError("No API key found in LLM config")
        
        # Add debug logging to see what key is being used (first 8 chars only for security)
        log.info(f"[llm] Using API key starting with: {api_key[:8]}... for provider {self.config.provider}")
        
        if self.config.provider.lower() == "openai":
            try:
                import openai
                return openai.OpenAI(api_key=api_key)
            except ImportError:
                raise RuntimeError("OpenAI package not installed. Run: pip install openai")
        
        elif self.config.provider.lower() == "anthropic":
            try:
                import anthropic
                return anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise RuntimeError("Anthropic package not installed. Run: pip install anthropic")
        
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config.provider}")
    
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
            
            if self.config.provider.lower() == "openai":
                return self._generate_openai_response(conversation_messages, system_prompt, client_id)
            elif self.config.provider.lower() == "anthropic":
                return self._generate_anthropic_response(conversation_messages, system_prompt, client_id)
            else:
                raise ValueError(f"Unsupported provider: {self.config.provider}")
        
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
        """Generate response using Anthropic Claude API"""
        messages = []
        
        # Convert conversation to Anthropic format
        for msg in conversation_messages:
            if msg.role in ["user", "assistant"]:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Define enhanced tools for Claude using all available tools
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
                max_tokens=1024,
                temperature=self.config.temperature,
                system=system_prompt or "You are a helpful AI assistant for Windows system administration with access to powerful PowerShell tools.",
                messages=messages,
                tools=tools
            )
        except Exception as e:
            log.error(f"[llm] Anthropic API call failed: {e}")
            raise e
        
        # Check if tool was used
        if response.content and len(response.content) > 0:
            content_block = response.content[0]
            
            if hasattr(content_block, 'type') and content_block.type == 'tool_use':
                return {
                    "content": f"I'll execute the {content_block.name} tool.",
                    "tool_name": content_block.name,
                    "tool_args": json.dumps(content_block.input)
                }
            else:
                return {
                    "content": content_block.text if hasattr(content_block, 'text') else str(content_block)
                }
        
        return {
            "content": "I apologize, but I couldn't generate a response."
        }
    
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