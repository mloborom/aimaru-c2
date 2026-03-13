# api/app/routes_chat.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func
from datetime import datetime, timezone
import uuid
import logging
import base64
import re
import time

from Crypto.Cipher import AES

from .deps import get_db
from .auth_dep import require_role
from .models import ClientChatSession, ChatMessage, LLMConfig, User, Instruction
from .llm_service import LLMService
from .crypto_runtime import RING

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.post("/sessions")
def create_chat_session(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Create a new chat session for a client"""
    client_id = payload.get("client_id")
    llm_config_id = payload.get("llm_config_id")
    system_prompt = payload.get("system_prompt")
    
    if not client_id:
        raise HTTPException(400, "client_id is required")
    
    # Verify LLM config exists and belongs to user or is shared
    if llm_config_id:
        llm_config = db.get(LLMConfig, llm_config_id)
        if not llm_config:
            raise HTTPException(404, "LLM config not found")
        if llm_config.owner_user_id and llm_config.owner_user_id != user.id:
            raise HTTPException(403, "Access denied to LLM config")
        if not llm_config.is_active:
            raise HTTPException(400, "LLM config is not active")
    
    # Create session
    session = ClientChatSession(
        client_id=client_id,
        owner_user_id=user.id,
        llm_config_id=llm_config_id,
        system_prompt=system_prompt
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    log.info(f"[chat] Created session {session.id} for client {client_id} by user {user.id}")
    
    return {
        "id": str(session.id),
        "client_id": session.client_id,
        "llm_config_id": str(session.llm_config_id) if session.llm_config_id else None,
        "system_prompt": session.system_prompt,
        "created_at": session.created_at.isoformat()
    }

@router.get("/sessions")
def list_chat_sessions(
    client_id: str = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """List chat sessions for the current user"""
    query = select(ClientChatSession).where(
        ClientChatSession.owner_user_id == user.id
    ).order_by(desc(ClientChatSession.created_at)).limit(limit)
    
    if client_id:
        query = query.where(ClientChatSession.client_id == client_id)
    
    sessions = db.execute(query).scalars().all()
    
    # Get message counts and last message times
    result = []
    for session in sessions:
        message_count = db.execute(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.session_id == session.id
            )
        ).scalar() or 0
        
        last_message = db.execute(
            select(ChatMessage.created_at).where(
                ChatMessage.session_id == session.id
            ).order_by(desc(ChatMessage.created_at)).limit(1)
        ).scalar()
        
        result.append({
            "id": str(session.id),
            "client_id": session.client_id,
            "llm_config_id": str(session.llm_config_id) if session.llm_config_id else None,
            "system_prompt": session.system_prompt,
            "created_at": session.created_at.isoformat(),
            "message_count": message_count,
            "last_message_at": last_message.isoformat() if last_message else None
        })
    
    return {"sessions": result}

@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Get messages for a chat session with automatic instruction result checking"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(400, "Invalid session ID format")

    # Verify session belongs to user
    session = db.execute(
        select(ClientChatSession).where(
            ClientChatSession.id == session_uuid,
            ClientChatSession.owner_user_id == user.id
        )
    ).scalar_one_or_none()

    if not session:
        raise HTTPException(404, "Chat session not found")

    messages = db.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == session_uuid
        ).order_by(ChatMessage.created_at).limit(limit)
    ).scalars().all()

    # Check for tool messages with instruction IDs that have completed
    log.info(f"[chat] Checking {len(messages)} messages for completed instructions in session {session_id}")
    for msg in messages:
        log.debug(f"[chat] Message role: {msg.role}, has content: {bool(msg.content)}, has 'Instruction ID': {'Instruction ID:' in (msg.content or '')}")
        if msg.role == "tool" and msg.content and "Instruction ID:" in msg.content:
            log.info(f"[chat] Found tool message with instruction ID: {msg.id}")
            # Extract instruction ID from tool message
            match = re.search(r'Instruction ID: ([a-f0-9-]+)', msg.content)
            if match:
                instruction_id_str = match.group(1)
                try:
                    instruction_uuid = uuid.UUID(instruction_id_str)

                    # Check if instruction is completed
                    instruction = db.get(Instruction, instruction_uuid)
                    if instruction and instruction.status == "completed":
                        # Check if we already added a result message for this instruction
                        existing_result = db.execute(
                            select(ChatMessage).where(
                                ChatMessage.session_id == session_uuid,
                                ChatMessage.role == "system",
                                ChatMessage.content.like(f"%{instruction_id_str}%")
                            )
                        ).scalar_one_or_none()

                        if not existing_result:
                            # Decrypt result from result_cipher
                            result_content = ""
                            if instruction.result_cipher:
                                # Decrypt the result using the same logic as routes_mcp.py
                                got = RING.get_enc(instruction.client_id)
                                if got:
                                    kid, enc_key = got
                                    try:
                                        if len(instruction.result_cipher) >= 17:
                                            iv = instruction.result_cipher[:16]
                                            ct = instruction.result_cipher[16:]

                                            cipher = AES.new(enc_key, AES.MODE_CBC, iv=iv)
                                            pt = cipher.decrypt(ct)

                                            # PKCS#7 unpad
                                            pad_len = pt[-1]
                                            if 1 <= pad_len <= 16 and all(b == pad_len for b in pt[-pad_len:]):
                                                pt = pt[:-pad_len]
                                                result_content = pt.decode('utf-8')
                                            else:
                                                result_content = "Error: Invalid padding in encrypted result"
                                        else:
                                            result_content = "Error: Ciphertext too short"
                                    except Exception as e:
                                        result_content = f"Error decrypting result: {e}"
                                        log.warning(f"[chat] Failed to decrypt result for instruction {instruction_id_str}: {e}")
                                else:
                                    result_content = "Error: No encryption key available for this client"
                                    log.warning(f"[chat] No encryption key for client {instruction.client_id}")
                            else:
                                result_content = "No result available"

                            # Detect if result contains errors or no data for session memory
                            content_lower = result_content.lower()
                            result_stripped = result_content.strip()

                            # Check for explicit errors
                            is_error = any(keyword in content_lower for keyword in [
                                'error', 'exception', 'failed', 'cannot', 'not found',
                                'access denied', 'permission', 'invalid', 'could not',
                                'unauthorized', 'forbidden', 'does not exist'
                            ])

                            # Check for no output (empty or just whitespace)
                            is_no_output = (
                                result_stripped == '' or
                                result_stripped == '<no output>' or
                                result_stripped.lower() in ['no result available', 'no output']
                            )

                            # Create formatted result message with error/no-data detection
                            if is_error:
                                status_emoji = "❌"
                                status_text = "ERROR DETECTED"
                            elif is_no_output:
                                status_emoji = "⚠️"
                                status_text = "NO OUTPUT"
                            else:
                                status_emoji = "✅"
                                status_text = "SUCCESS"

                            result_message_content = f"{status_emoji} **PowerShell Execution Result - {status_text}** (ID: {instruction_id_str})\n\n```\n{result_content}\n```"

                            if is_error:
                                result_message_content += "\n\n💡 **Tip**: Analyze the error above and try an alternative PowerShell approach to achieve the same goal."
                            elif is_no_output:
                                result_message_content += "\n\n💡 **Tip**: The command executed but returned no data. This could mean:\n- No items matched your filter/query\n- The path/resource doesn't exist\n- Permissions are preventing data retrieval\nTry a different query approach or check if the resource exists."

                            result_message = ChatMessage(
                                session_id=session_uuid,
                                role="system",
                                content=result_message_content,
                                created_at=instruction.completed_at or instruction.created_at
                            )
                            db.add(result_message)
                            db.commit()
                            db.refresh(result_message)

                            # Add to messages list
                            messages.append(result_message)
                            log.info(f"[chat] Added instruction result {instruction_id_str} to session {session_id} (status={status_text})")

                            # AUTO-ITERATE: If error or no output detected, trigger LLM to try alternatives automatically
                            # ENHANCED AGENTIC AUTO-ITERATION: Multi-step iteration with learning and escalation
                            if (is_error or is_no_output) and session.llm_config_id:
                                log.info(f"[chat] Auto-iteration triggered for {status_text} in session {session_id}")

                                # Configuration
                                MAX_AUTO_ITERATIONS = 5  # Maximum automatic retry attempts

                                # Track iteration state (in session scope)
                                iteration_count = 1  # This is the first auto-iteration attempt
                                success = False

                                # Complexity escalation levels
                                complexity_levels = [
                                    "PowerShell cmdlets with broader filters",
                                    "WMI queries (Get-WmiObject/Get-CimInstance)",
                                    "Registry access (HKLM/HKCU paths)",
                                    "Windows LOLBins (certutil, wmic, net, reg, tasklist, netsh)",
                                    "PowerShell scripts or trusted Microsoft SysInternals tools"
                                ]

                                try:
                                    llm_config = db.get(LLMConfig, session.llm_config_id)
                                    if llm_config and llm_config.is_active:
                                        # Get updated conversation history including the result we just added
                                        conversation_messages = db.execute(
                                            select(ChatMessage).where(
                                                ChatMessage.session_id == session_uuid
                                            ).order_by(ChatMessage.created_at)
                                        ).scalars().all()

                                        # Extract previously failed commands from conversation history
                                        # This prevents the LLM from repeating the same failed approaches
                                        failed_commands = []
                                        for msg in conversation_messages:
                                            if msg.role == "tool" and msg.tool_name == "execute_powershell":
                                                # Check if this tool message was followed by error/no-output
                                                msg_index = list(conversation_messages).index(msg)
                                                if msg_index + 1 < len(conversation_messages):
                                                    next_msg = conversation_messages[msg_index + 1]
                                                    if "ERROR DETECTED" in next_msg.content or "NO OUTPUT" in next_msg.content:
                                                        # This command failed, extract it
                                                        if isinstance(msg.tool_args, str):
                                                            import json
                                                            try:
                                                                args = json.loads(msg.tool_args)
                                                                failed_cmd = args.get("powershell_script", "")
                                                                if failed_cmd and failed_cmd not in failed_commands:
                                                                    failed_commands.append(failed_cmd)
                                                            except:
                                                                pass
                                                        elif isinstance(msg.tool_args, dict):
                                                            failed_cmd = msg.tool_args.get("powershell_script", "")
                                                            if failed_cmd and failed_cmd not in failed_commands:
                                                                failed_commands.append(failed_cmd)

                                        log.info(f"[chat] Auto-iteration: Found {len(failed_commands)} previously failed commands")

                                        # Determine current complexity level (escalate based on number of failures)
                                        current_level_index = min(len(failed_commands), len(complexity_levels) - 1)
                                        suggested_approach = complexity_levels[current_level_index]

                                        # Build failed approaches context
                                        failed_approaches_text = ""
                                        if failed_commands:
                                            failed_approaches_text = "\n\nPREVIOUSLY FAILED APPROACHES (DO NOT REPEAT THESE):\n"
                                            for idx, cmd in enumerate(failed_commands, 1):
                                                # Truncate long commands for readability
                                                display_cmd = cmd if len(cmd) < 100 else cmd[:100] + "..."
                                                failed_approaches_text += f"{idx}. {display_cmd}\n"
                                            failed_approaches_text += "\nYou MUST use a fundamentally different approach than these failed attempts.\n"

                                        # Build complexity escalation guidance
                                        escalation_guidance = f"\n\nRECOMMENDED COMPLEXITY LEVEL FOR THIS ATTEMPT:\n{suggested_approach}\n"
                                        if current_level_index > 0:
                                            escalation_guidance += f"\nNOTE: Simpler approaches have failed. Escalate to more advanced methods.\n"

                                        # Create enhanced auto-iteration prompt based on failure type
                                        if is_no_output:
                                            auto_prompt = f"""CRITICAL INSTRUCTION - IMMEDIATE ACTION REQUIRED:

The previous PowerShell command returned NO OUTPUT. This is a failure condition.

ITERATION STATUS: Attempt {iteration_count + len(failed_commands)}/{MAX_AUTO_ITERATIONS}
{failed_approaches_text}{escalation_guidance}
YOUR MANDATORY NEXT ACTION: You MUST immediately call the execute_powershell tool with a COMPLETELY DIFFERENT command.

STRICT RULES - SECURITY OPERATIONAL DISCIPLINE:
- ONLY use NATIVE Windows tools (PowerShell cmdlets, WMI, registry, built-in utilities)
- ONLY use Windows LOLBins: certutil.exe, wmic.exe, net.exe, reg.exe, tasklist.exe, netsh.exe, bitsadmin.exe, sc.exe
- NEVER suggest downloading tools (nmap, netcat, mimikatz, etc.) - these trigger security alerts
- NEVER use external/third-party tools that don't come with Windows by default
- If a tool isn't native to Windows, DO NOT USE IT

DO NOT:
- Do NOT explain without executing
- Do NOT say "I will try" or "let me try"
- Do NOT repeat ANY of the previously failed commands above
- Do NOT just acknowledge the failure
- Do NOT suggest non-native tools

YOU MUST:
1. Analyze why no output occurred (wrong filter, wrong path, resource doesn't exist)
2. Generate a FUNDAMENTALLY DIFFERENT PowerShell command using ONLY native approaches:
   - Remove or broaden the Where-Object filter
   - Try DIFFERENT registry paths (HKLM:\\SOFTWARE\\WOW6432Node for 32-bit apps)
   - Use WMI: Get-WmiObject Win32_{{Class}} or Get-CimInstance
   - Use registry: Get-ItemProperty with alternative paths
   - Use native utilities ONLY: net.exe, netsh.exe, tasklist.exe, sc.exe, reg.exe
3. CALL execute_powershell with your new NATIVE command RIGHT NOW

RESPOND WITH: Brief 1-sentence explanation of what you're changing, then immediately call execute_powershell tool with the new command."""
                                        else:  # is_error
                                            auto_prompt = f"""CRITICAL INSTRUCTION - IMMEDIATE ACTION REQUIRED:

The previous PowerShell command FAILED WITH AN ERROR. This is a failure condition.

ITERATION STATUS: Attempt {iteration_count + len(failed_commands)}/{MAX_AUTO_ITERATIONS}
{failed_approaches_text}{escalation_guidance}
YOUR MANDATORY NEXT ACTION: You MUST immediately call the execute_powershell tool with a COMPLETELY DIFFERENT approach.

OPERATIONAL SECURITY RULES - TRUSTED TOOLS ONLY:
- ONLY use tools that are TRUSTED in enterprise Windows environments
- NEVER use security/hacking tools: nmap, netcat, mimikatz, psexec, cobalt strike, metasploit, etc.
- If you need advanced capabilities (port scanning, network analysis):
  * OPTION 1: Write PowerShell script to emulate the functionality
  * OPTION 2: Use Microsoft SysInternals tools (trusted, signed by Microsoft)
  * OPTION 3: Use built-in Windows cmdlets/utilities
- Prefer: PowerShell cmdlets > WMI > Windows LOLBins > PowerShell scripts > trusted Microsoft tools

DO NOT:
- Do NOT explain without executing
- Do NOT say "I will try" or "let me try"
- Do NOT repeat ANY of the previously failed commands above
- Do NOT just acknowledge the error
- Do NOT suggest downloading non-Microsoft security tools

YOU MUST:
1. Analyze the specific error message (permissions, missing module, wrong cmdlet, etc.)
2. Generate a FUNDAMENTALLY DIFFERENT PowerShell command using TRUSTED approaches:
   - Use DIFFERENT cmdlets (if Get-* failed, try WMI: Get-WmiObject or Get-CimInstance)
   - If PowerShell module missing: Use Windows utilities (net.exe, reg.exe, wmic.exe, tasklist.exe, netsh.exe)
   - If execution policy restricted: Use Windows LOLBins (certutil, wmic, net, reg, bitsadmin)
   - If advanced capability needed: Write PowerShell script to emulate it or use SysInternals tools
3. CALL execute_powershell with your new TRUSTED command RIGHT NOW

RESPOND WITH: Brief 1-sentence explanation of the error cause and your fix, then immediately call execute_powershell tool with the new command."""

                                        # Create auto-iteration message for LLM context ONLY (not saved to DB, not shown to user)
                                        # This is a transient message object that only exists in memory for the LLM call
                                        # IMPORTANT: Must be "user" role because llm_service.py skips "system" messages (line 139-142)
                                        class TransientMessage:
                                            def __init__(self, role, content):
                                                self.role = role
                                                self.content = content
                                                self.created_at = datetime.now(timezone.utc)

                                        auto_message = TransientMessage("user", auto_prompt)  # USER role so LLM sees it!
                                        # DO NOT save to DB - this keeps it invisible to user

                                        # Call LLM service to generate alternative approach
                                        llm_service = LLMService(llm_config)

                                        # Update conversation messages to include auto-iteration prompt
                                        conversation_messages = list(conversation_messages) + [auto_message]

                                        # Show progress with iteration counter and complexity level
                                        failure_type = "no data" if is_no_output else "an error"
                                        current_attempt = iteration_count + len(failed_commands)

                                        # Progress message with attempt counter and escalation info
                                        if len(failed_commands) == 0:
                                            generating_msg = f"🤖 **Attempt {current_attempt}/{MAX_AUTO_ITERATIONS}** - Generating alternative approach... The previous command returned {failure_type}."
                                        else:
                                            generating_msg = f"🤖 **Attempt {current_attempt}/{MAX_AUTO_ITERATIONS}** - Escalating to: {suggested_approach}. Previous {len(failed_commands)} attempt{'s' if len(failed_commands) > 1 else ''} failed."

                                        time.sleep(0.001)
                                        generating_message = ChatMessage(
                                            session_id=session_uuid,
                                            role="system",
                                            content=generating_msg,
                                            created_at=datetime.now(timezone.utc)
                                        )
                                        db.add(generating_message)
                                        db.commit()
                                        messages.append(generating_message)

                                        # Generate LLM response with auto-iteration context
                                        response = llm_service.generate_response(
                                            conversation_messages,
                                            session.system_prompt,
                                            session.client_id
                                        )

                                        log.info(f"[chat] Auto-iteration LLM response: tool={response.get('tool_name')}, content_length={len(response.get('content', ''))}")
                                        if not response.get('tool_name'):
                                            log.warning(f"[chat] Auto-iteration: LLM did not generate tool call! Response content: {response.get('content', '')[:200]}")

                                        # Add assistant response with actual strategy
                                        time.sleep(0.001)  # Ensure different timestamp
                                        assistant_content = response.get("content", "I'll try an alternative approach.")
                                        assistant_message = ChatMessage(
                                            session_id=session_uuid,
                                            role="assistant",
                                            content=assistant_content,
                                            tool_name=response.get("tool_name"),
                                            tool_args=response.get("tool_args"),
                                            created_at=datetime.now(timezone.utc)
                                        )
                                        db.add(assistant_message)
                                        db.commit()
                                        messages.append(assistant_message)

                                        # Execute tool if suggested
                                        log.info(f"[chat] Auto-iteration checking for tool call: tool_name={response.get('tool_name')}, has_tool_args={response.get('tool_args') is not None}")
                                        if response.get("tool_name"):
                                            log.info(f"[chat] Auto-iteration CONFIRMED executing tool: {response.get('tool_name')}")

                                            # Extract PowerShell command from tool_args to show user
                                            # tool_args might be a JSON string, parse it if needed
                                            tool_args = response.get("tool_args", {})
                                            if isinstance(tool_args, str):
                                                import json
                                                try:
                                                    tool_args = json.loads(tool_args)
                                                except json.JSONDecodeError:
                                                    log.warning(f"[chat] Auto-iteration: Failed to parse tool_args JSON: {tool_args}")
                                                    tool_args = {}
                                            ps_script = tool_args.get("powershell_script", "")

                                            log.info(f"[chat] Auto-iteration PowerShell script length: {len(ps_script) if ps_script else 0}")

                                            # Execute tool first (MUST come immediately after assistant message with tool_calls for OpenAI API)
                                            log.info(f"[chat] Auto-iteration calling execute_tool with: tool_name={response.get('tool_name')}, client_id={session.client_id}")
                                            tool_result = llm_service.execute_tool(
                                                response.get("tool_name"),
                                                response.get("tool_args"),
                                                session.client_id,
                                                db,
                                                user,  # Use user from function parameter
                                                conversation_messages
                                            )
                                            log.info(f"[chat] Auto-iteration execute_tool returned: {tool_result is not None}")

                                            if tool_result:
                                                time.sleep(0.001)  # Ensure different timestamp
                                                tool_content = tool_result.get("content", "Tool executed")
                                                if tool_result.get("execution_details"):
                                                    details = tool_result["execution_details"]
                                                    if details.get("instruction_id"):
                                                        tool_content += f"\nInstruction ID: {details['instruction_id']}"

                                                tool_message = ChatMessage(
                                                    session_id=session_uuid,
                                                    role="tool",
                                                    content=tool_content,
                                                    tool_name=response.get("tool_name"),
                                                    tool_args=response.get("tool_args"),
                                                    created_at=datetime.now(timezone.utc)
                                                )
                                                db.add(tool_message)
                                                db.commit()
                                                messages.append(tool_message)
                                                log.info(f"[chat] Auto-iteration tool executed successfully: {tool_content[:100]}")

                                                # NOW show user what command was executed (AFTER tool message to satisfy OpenAI API rules)
                                                if ps_script:
                                                    time.sleep(0.001)
                                                    display_script = ps_script if len(ps_script) < 300 else ps_script[:300] + "..."
                                                    execution_notice = f"⚡ **Alternative command executed:**\n```powershell\n{display_script}\n```"

                                                    notice_message = ChatMessage(
                                                        session_id=session_uuid,
                                                        role="system",
                                                        content=execution_notice,
                                                        created_at=datetime.now(timezone.utc)
                                                    )
                                                    db.add(notice_message)
                                                    db.commit()
                                                    messages.append(notice_message)
                                                    log.info(f"[chat] Auto-iteration showing executed command to user")

                                                # Check if we've reached max iterations
                                                total_attempts = iteration_count + len(failed_commands)
                                                if total_attempts >= MAX_AUTO_ITERATIONS:
                                                    time.sleep(0.001)
                                                    max_reached_msg = f"ℹ️ **Maximum auto-iteration attempts reached** ({MAX_AUTO_ITERATIONS}/{MAX_AUTO_ITERATIONS}). The command has been queued and will execute on the client. If this attempt also fails, you may need to manually refine your request or try a different approach."

                                                    max_message = ChatMessage(
                                                        session_id=session_uuid,
                                                        role="system",
                                                        content=max_reached_msg,
                                                        created_at=datetime.now(timezone.utc)
                                                    )
                                                    db.add(max_message)
                                                    db.commit()
                                                    messages.append(max_message)
                                                    log.info(f"[chat] Auto-iteration: Maximum attempts ({MAX_AUTO_ITERATIONS}) reached")
                                            else:
                                                log.warning(f"[chat] Auto-iteration: execute_tool returned None or empty result")
                                        else:
                                            log.warning(f"[chat] Auto-iteration: No tool_name found in response! Full response: {response}")

                                except Exception as e:
                                    log.error(f"[chat] Auto-iteration failed: {e}")
                                    import traceback
                                    log.error(f"[chat] Auto-iteration traceback: {traceback.format_exc()}")
                                    # Don't add error message to avoid confusing user - just log it

                except (ValueError, AttributeError) as e:
                    log.debug(f"[chat] Could not process instruction ID: {e}")

    # Re-sort messages by created_at after potentially adding new ones
    messages = sorted(messages, key=lambda m: m.created_at)

    return {
        "session_id": session_id,
        "messages": [
            {
                "id": str(msg.id),
                "session_id": str(msg.session_id),
                "role": msg.role,
                "content": msg.content,
                "tool_name": msg.tool_name,
                "tool_args": msg.tool_args,
                "created_at": msg.created_at.isoformat()
            }
            for msg in messages
        ]
    }

@router.post("/message")
def send_chat_message(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Send a message in a chat session and get LLM response"""
    session_id = payload.get("session_id")
    message_content = payload.get("message")
    message_role = payload.get("role", "user")
    
    if not session_id or not message_content:
        raise HTTPException(400, "session_id and message are required")
    
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(400, "Invalid session ID format")
    
    # Verify session belongs to user
    session = db.execute(
        select(ClientChatSession).where(
            ClientChatSession.id == session_uuid,
            ClientChatSession.owner_user_id == user.id
        )
    ).scalar_one_or_none()
    
    if not session:
        raise HTTPException(404, "Chat session not found")
    
    # Add user message
    user_message = ChatMessage(
        session_id=session_uuid,
        role=message_role,
        content=message_content
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    
    log.info(f"[chat] User message added to session {session_id}")
    
    # Get LLM response if this is a user message and we have an LLM config
    if message_role == "user" and session.llm_config_id:
        try:
            llm_config = db.get(LLMConfig, session.llm_config_id)
            if llm_config and llm_config.is_active:
                # Get conversation history
                conversation_messages = db.execute(
                    select(ChatMessage).where(
                        ChatMessage.session_id == session_uuid
                    ).order_by(ChatMessage.created_at)
                ).scalars().all()
                
                # Call LLM service with enhanced capabilities
                llm_service = LLMService(llm_config)
                response = llm_service.generate_response(
                    conversation_messages,
                    session.system_prompt,
                    session.client_id
                )
                
                # Add assistant response
                assistant_message = ChatMessage(
                    session_id=session_uuid,
                    role="assistant",
                    content=response.get("content", "I apologize, but I couldn't generate a response."),
                    tool_name=response.get("tool_name"),
                    tool_args=response.get("tool_args")
                )
                db.add(assistant_message)
                db.commit()
                
                # Execute tool if suggested (enhanced version)
                if response.get("tool_name"):
                    try:
                        log.info(f"[chat] Executing tool: {response.get('tool_name')}")
                        
                        tool_result = llm_service.execute_tool(
                            response.get("tool_name"),
                            response.get("tool_args"),
                            session.client_id,
                            db,
                            user,
                            conversation_messages  # Pass conversation context for intelligence
                        )
                        
                        # Add tool result message with enhanced formatting
                        if tool_result:
                            tool_content = tool_result.get("content", "Tool executed")
                            
                            # Add execution details if available
                            if tool_result.get("execution_details"):
                                details = tool_result["execution_details"]
                                if details.get("explanation"):
                                    tool_content += f"\n\nExplanation: {details['explanation']}"
                                if details.get("expected_outcome"):
                                    tool_content += f"\nExpected outcome: {details['expected_outcome']}"
                                if details.get("instruction_id"):
                                    tool_content += f"\nInstruction ID: {details['instruction_id']}"
                            
                            # Add safety warning if present
                            if tool_result.get("safety_warning"):
                                tool_content = f"⚠️ SAFETY WARNING: {tool_content}"
                            
                            tool_message = ChatMessage(
                                session_id=session_uuid,
                                role="tool",
                                content=tool_content,
                                tool_name=response.get("tool_name"),
                                tool_args=response.get("tool_args")
                            )
                            db.add(tool_message)
                            
                        else:
                            # Add error message if tool execution failed
                            error_message = ChatMessage(
                                session_id=session_uuid,
                                role="system",
                                content="Tool execution failed - no result returned"
                            )
                            db.add(error_message)
                            
                    except Exception as e:
                        log.error(f"[chat] Tool execution failed: {e}")
                        # Add error message with more detail
                        error_message = ChatMessage(
                            session_id=session_uuid,
                            role="system",
                            content=f"Tool execution failed: {str(e)}"
                        )
                        db.add(error_message)
                
                db.commit()
                log.info(f"[chat] LLM response added to session {session_id}")
        
        except Exception as e:
            log.error(f"[chat] LLM generation failed: {e}")
            # Add error message
            error_message = ChatMessage(
                session_id=session_uuid,
                role="system",
                content="I'm sorry, I encountered an error while processing your message. Please try again."
            )
            db.add(error_message)
            db.commit()
    
    return {
        "success": True,
        "message_id": str(user_message.id),
        "session_id": session_id
    }

@router.delete("/sessions/{session_id}")
def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Delete a chat session and all its messages"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(400, "Invalid session ID format")
    
    # Verify session belongs to user
    session = db.execute(
        select(ClientChatSession).where(
            ClientChatSession.id == session_uuid,
            ClientChatSession.owner_user_id == user.id
        )
    ).scalar_one_or_none()
    
    if not session:
        raise HTTPException(404, "Chat session not found")
    
    # Delete messages first (cascade should handle this, but being explicit)
    db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_uuid)
    )
    
    # Delete session
    db.delete(session)
    db.commit()
    
    log.info(f"[chat] Deleted session {session_id} by user {user.id}")
    
    return {"success": True, "deleted_session_id": session_id}