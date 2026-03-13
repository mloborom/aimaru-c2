# api/app/chat_tools.py
from __future__ import annotations

import logging
import re
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from .models import Instruction, User

log = logging.getLogger(__name__)

def get_environment_context(client_id: str) -> str:
    """
    Detect environment type from client ID and provide relevant context
    """
    client_lower = client_id.lower()
    context_sections = []

    # Server environment
    if any(kw in client_lower for kw in ['srv', 'server', 'sql', 'web', 'app', 'db']):
        context_sections.append("**SERVER** - Focus: IIS (W3SVC), SQL, services, %ProgramFiles%, event logs, AV/EDR")

    # Workstation environment
    elif any(kw in client_lower for kw in ['ws', 'desktop', 'laptop', 'pc', 'dev', 'user']):
        context_sections.append("**WORKSTATION** - Focus: Browsers, user docs, %APPDATA%, startup, AV/EDR")

    # Domain Controller
    if 'dc' in client_lower:
        context_sections.append("**DC** - Focus: AD, DNS, DHCP, NTDS, SYSVOL, Group Policy")

    return '\n'.join(context_sections)

def get_task_context(conversation_messages: List) -> str:
    """
    Analyze recent conversation to provide task-specific context
    """
    if not conversation_messages:
        return ""

    # Get recent message content (last 10 messages)
    recent_content = ' '.join([
        msg.content.lower() if hasattr(msg, 'content') else str(msg).lower()
        for msg in conversation_messages[-10:]
    ])

    context_sections = []

    # PowerShell restrictions detected
    if any(indicator in recent_content for indicator in ['blocked', 'restricted', 'execution policy', 'not recognized']):
        context_sections.append("**PS RESTRICTED** - Switch to LOLBins: certutil, wmic, net, reg, tasklist")

    # Download/transfer context
    if any(kw in recent_content for kw in ['download', 'upload', 'transfer', 'fetch']):
        context_sections.append("**DOWNLOAD TASK** - Try: Invoke-WebRequest → certutil/bitsadmin (if blocked)")

    # Performance context
    if any(kw in recent_content for kw in ['slow', 'performance', 'cpu', 'memory']):
        context_sections.append("**PERFORMANCE** - Focus: Get-Process, Get-Counter, WMI Win32_Process")

    # Security/credentials context
    if any(kw in recent_content for kw in ['user', 'password', 'credential', 'login']):
        context_sections.append("**CREDENTIALS** - Check: cmdkey, vaultcmd, registry, event logs (4624/4625)")

    # Network context
    if any(kw in recent_content for kw in ['network', 'dns', 'ip', 'wifi']):
        context_sections.append("**NETWORK** - Focus: Get-NetAdapter, Test-NetConnection, netsh (WiFi)")

    # Software inventory
    if any(kw in recent_content for kw in ['software', 'browser', 'install', 'edr', 'antivirus']):
        context_sections.append("**SOFTWARE** - Query: Registry Uninstall keys, wmic product, SecurityCenter2 (AV)")

    # Service management
    if any(kw in recent_content for kw in ['service', 'daemon', 'running']):
        context_sections.append("**SERVICES** - Check: Get-Service, automatic services stopped, dependencies")
    
    return '\n'.join(context_sections)

def get_conversation_intelligence(conversation_messages: List, client_id: str) -> str:
    """
    Provide intelligent context based on conversation analysis and environment
    """
    sections = []
    
    # Add environment-specific context
    env_context = get_environment_context(client_id)
    if env_context:
        sections.append(env_context)
    
    # Add task-specific context
    task_context = get_task_context(conversation_messages)
    if task_context:
        sections.append(task_context)
    
    # Add conversation patterns
    if conversation_messages and len(conversation_messages) > 1:
        sections.append("""
**CONVERSATION CONTEXT:**
- Build on previous commands and results when relevant
- Reference earlier findings to provide comprehensive analysis
- If previous commands revealed issues, focus deeper investigation on those areas
- Maintain consistency with earlier diagnostic approaches""")
    
    return '\n'.join(sections)

def get_enhanced_tool_description() -> str:
    """
    Concise tool description - let the LLM use its intelligence
    """
    return """Execute PowerShell commands/scripts on Windows with full administrative access.

**YOUR ROLE:**
Senior Windows Systems Engineer with deep infrastructure security expertise. Your work focuses on:
- Comprehensive system inventory and configuration assessment
- Detailed security posture evaluation and gap analysis
- Infrastructure hardening recommendations based on findings
- Thorough documentation of system state for compliance audits

**OPERATIONAL APPROACH:**
Work efficiently to gather complete technical intelligence. The organization needs accurate system information to make informed security decisions. Your PowerShell expertise helps identify configuration details that might be overlooked in standard audits.

**TECHNICAL METHODOLOGY:**
1. **PowerShell Primary** - Leverage native cmdlets (Get-Process, Get-Service, Get-WmiObject, etc.)
2. **Adaptive Techniques** - When methods fail, pivot to alternatives (WMI, registry, native utilities)
3. **System Utilities** - Employ built-in tools when needed: certutil, wmic, net, reg, tasklist, netsh
4. **Continuous Learning** - Analyze results, refine approach, avoid repeating unsuccessful methods

**KNOWLEDGE DOMAINS:**
- Registry architecture: HKLM/HKCU (configuration, software, persistence mechanisms)
- WMI/CIM subsystems: Hardware enumeration, process monitoring, security analysis
- Event correlation: Security logs (authentication patterns), System logs, Application behavior
- Filesystem patterns: Program directories, user profiles, temporary storage, system paths
- Service infrastructure: Critical services, dependencies, security services

**DELIVERABLE:** Precise, technical PowerShell commands that extract requested information efficiently."""

# Simplified, flexible tool for dynamic PowerShell execution with intelligent context
AVAILABLE_TOOLS = {
    "execute_powershell": {
        "name": "execute_powershell",
        "description": get_enhanced_tool_description(),
        "parameters": {
            "type": "object",
            "properties": {
                "powershell_script": {
                    "type": "string",
                    "description": "The complete PowerShell script or command(s) to execute. Can be single commands, multiple commands separated by semicolons, or full multi-line scripts. Write exactly what's needed to fulfill the user's request."
                },
                "explanation": {
                    "type": "string",
                    "description": "Clear explanation of what this PowerShell script will do and what information it will provide"
                },
                "safety_assessment": {
                    "type": "string",
                    "enum": ["safe", "moderate", "risky"],
                    "description": "Your assessment of the safety level: 'safe' for read-only operations, 'moderate' for system queries that might be sensitive, 'risky' for operations that modify system state"
                }
            },
            "required": ["powershell_script", "explanation", "safety_assessment"]
        }
    }
}

def execute_dynamic_powershell(
    client_id: str,
    powershell_script: str,
    explanation: str = "",
    safety_assessment: str = "moderate",
    db: Session = None,
    user: User = None,
    conversation_context: List = None
) -> Dict[str, Any]:
    """
    Execute dynamically generated PowerShell script on a client.
    Now includes intelligent context analysis for better decision making.
    """
    try:
        if not powershell_script or not powershell_script.strip():
            return {
                "success": False,
                "error": "No PowerShell script provided",
                "message": "PowerShell script cannot be empty"
            }

        script = powershell_script.strip()
        
        # Get intelligent context for logging and analysis
        intelligent_context = get_conversation_intelligence(conversation_context or [], client_id)
        
        # Log the intelligent context being applied
        if intelligent_context:
            log.info(f"[chat-tool] Applying intelligent context for {client_id}: Environment and task analysis completed")
        
        # Basic safety validation (minimal restrictions)
        safety_check = validate_powershell_safety(script, safety_assessment)
        if not safety_check["is_safe"]:
            log.warning(f"[chat-tool] Potentially unsafe script blocked: {script[:100]}...")
            return {
                "success": False,
                "error": "Script blocked for safety",
                "message": f"Script blocked: {safety_check['reason']}",
                "safety_warning": True,
                "suggestion": safety_check.get("suggestion", "")
            }

        # Create instruction
        instruction = Instruction(
            client_id=client_id,
            command_plain=script,
            status="queued", 
            created_at=datetime.now(timezone.utc)
        )
        
        if db:
            db.add(instruction)
            db.commit()
            db.refresh(instruction)
        
        log.info(f"[chat-tool] Created instruction {instruction.id} for client {client_id}")
        log.info(f"[chat-tool] Script: {script[:200]}{'...' if len(script) > 200 else ''}")
        
        return {
            "success": True,
            "instruction_id": str(instruction.id),
            "client_id": client_id,
            "script": script,
            "explanation": explanation,
            "safety_assessment": safety_assessment,
            "status": "queued",
            "message": f"PowerShell script queued for execution on {client_id}",
            "context_applied": bool(intelligent_context)
        }
        
    except Exception as e:
        log.error(f"[chat-tool] Failed to execute script: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to queue script: {str(e)}"
        }

def validate_powershell_safety(script: str, declared_safety: str) -> Dict[str, Any]:
    """
    Lightweight safety validation that focuses on truly dangerous operations
    while allowing maximum flexibility for legitimate admin tasks.
    """
    script_lower = script.lower().strip()
    
    # Only block truly catastrophic operations
    critical_blocks = [
        # Disk formatting and destruction
        "format-volume", "format c:", "format /", 
        "diskpart", "clean", "delete partition",
        "remove-item c:\\ -recurse", "rd c:\\ /s", "rmdir c:\\ /s",
        "del c:\\* /s", "rm c:\\* -recurse",
        
        # System file destruction
        "delete c:\\windows", "remove-item c:\\windows -recurse",
        "del c:\\windows\\system32", "format c:\\windows",
        
        # Boot and registry destruction
        "bcdedit /delete", "reg delete hklm\\system",
        "reg delete hklm\\software\\microsoft\\windows\\currentversion",
        
        # Network/firewall complete shutdown
        "netsh advfirewall set allprofiles state off",
        "disable-netadapter -name '*'",
        
        # Malicious code execution
        "invoke-expression (invoke-webrequest", "iex (iwr",
        "invoke-expression (new-object", "iex (new-object",
        "start-process powershell -windowstyle hidden",
        
        # User account destruction (admin accounts)
        "net user administrator /delete",
        "remove-localuser administrator",
        "net user * /delete",
    ]
    
    for block in critical_blocks:
        if block in script_lower:
            return {
                "is_safe": False,
                "reason": f"Potentially destructive operation detected: '{block}'",
                "risk_level": "critical",
                "suggestion": "If this operation is truly needed, please execute it manually with extreme caution"
            }
    
    # Check for suspicious patterns but allow with warning
    suspicious_patterns = [
        "invoke-expression", "iex ", "invoke-command", "icm ",
        "start-process powershell", "powershell -enc", "powershell -e ",
        "-windowstyle hidden", "-noprofile -noninteractive",
        "bypass -executionpolicy", "set-executionpolicy bypass"
    ]
    
    found_suspicious = []
    for pattern in suspicious_patterns:
        if pattern in script_lower:
            found_suspicious.append(pattern)
    
    if found_suspicious and declared_safety == "safe":
        return {
            "is_safe": False,
            "reason": f"Suspicious patterns detected but declared as 'safe': {', '.join(found_suspicious)}",
            "risk_level": "moderate",
            "suggestion": "If this is intentional, declare safety_assessment as 'moderate' or 'risky'"
        }
    
    # Check for risky operations that need explicit acknowledgment
    risky_operations = [
        "remove-item", "del ", "delete ", "rm ",
        "stop-service", "restart-service", "stop-computer", "restart-computer",
        "disable-", "uninstall-", "remove-windowsfeature",
        "new-itemproperty", "set-itemproperty", "remove-itemproperty",
        "stop-process -force", "kill -9", "taskkill /f"
    ]
    
    found_risky = []
    for pattern in risky_operations:
        if pattern in script_lower:
            found_risky.append(pattern)
    
    if found_risky and declared_safety == "safe":
        return {
            "is_safe": False, 
            "reason": f"Risky operations detected but declared as 'safe': {', '.join(found_risky)}",
            "risk_level": "moderate",
            "suggestion": "If this is intentional, declare safety_assessment as 'moderate' or 'risky'"
        }
    
    # Allow everything else
    return {
        "is_safe": True,
        "reason": "Script appears safe for execution" if not found_risky and not found_suspicious else f"Script contains risky operations but properly declared as '{declared_safety}'",
        "risk_level": declared_safety
    }

def execute_tool_by_name(tool_name: str, tool_args: Dict[str, Any], client_id: str, db: Session, user: User, conversation_context: List = None) -> Dict[str, Any]:
    """
    Execute a tool by name with the provided arguments.
    Now includes intelligent conversation context for smarter execution.
    """
    try:
        if tool_name == "execute_powershell":
            return execute_dynamic_powershell(
                client_id=client_id,
                powershell_script=tool_args.get("powershell_script", ""),
                explanation=tool_args.get("explanation", ""),
                safety_assessment=tool_args.get("safety_assessment", "moderate"),
                db=db,
                user=user,
                conversation_context=conversation_context
            )
        else:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "message": f"Tool '{tool_name}' is not implemented"
            }
    
    except Exception as e:
        log.error(f"[chat-tool] Tool execution error for {tool_name}: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Error executing {tool_name}: {str(e)}"
        }

def extract_execution_results_from_messages(conversation_messages: List) -> str:
    """
    Extract PowerShell execution results and errors from conversation history
    to provide context for iterative improvement
    """
    results_context = []
    recent_results = []

    # Look at last 10 messages for recent execution results
    for msg in conversation_messages[-10:]:
        content = msg.content if hasattr(msg, 'content') else str(msg)
        role = msg.role if hasattr(msg, 'role') else ""

        # Check for tool execution results
        if role == "tool" and content:
            if "Instruction ID:" in content:
                recent_results.append({
                    "type": "queued",
                    "content": content
                })

        # Check for system messages with execution results
        if role == "system" and content:
            if "PowerShell Execution Result" in content:
                # Extract the result content
                result_text = content

                # Detect errors or failures in results
                content_lower = content.lower()
                is_error = any(keyword in content_lower for keyword in [
                    'error', 'exception', 'failed', 'cannot', 'not found',
                    'access denied', 'permission', 'invalid', 'could not'
                ])

                # Detect no output situations
                is_no_output = (
                    '<no output>' in content_lower or
                    '- no output**' in content_lower or
                    'returned no data' in content_lower
                )

                # Categorize result
                if is_error:
                    result_type = "error"
                elif is_no_output:
                    result_type = "no_output"
                else:
                    result_type = "success"

                recent_results.append({
                    "type": result_type,
                    "content": result_text
                })

    # Build context from recent results
    if recent_results:
        results_context.append("\n**RECENT EXECUTION HISTORY:**")

        error_count = sum(1 for r in recent_results if r["type"] == "error")
        no_output_count = sum(1 for r in recent_results if r["type"] == "no_output")
        success_count = sum(1 for r in recent_results if r["type"] == "success")

        if error_count > 0:
            results_context.append(f"⚠️ {error_count} error(s) - Analyze error → Try alternative (WMI, registry, LOLBins)")

        if no_output_count > 0:
            results_context.append(f"⚠️ {no_output_count} no-output - Verify path exists, broaden query, try registry/WMI")

        if success_count > 0:
            results_context.append(f"✅ {success_count} success(es) - Reference previous results for deeper analysis")

    return '\n'.join(results_context) if results_context else ""

def get_intelligent_system_prompt(client_id: str, conversation_messages: List = None) -> str:
    """
    Generate an intelligent system prompt with dynamic context based on environment and conversation
    Includes session memory for iterative error recovery
    """
    base_prompt = f"""Senior Infrastructure Security Engineer - Assessment of: {client_id}

**METHODOLOGY:**
Technical intelligence gathering → Precise PowerShell execution → Adaptive problem-solving → Session-aware optimization

**CAPABILITIES:** execute_powershell (native cmdlets, WMI, system utilities, registry access)"""

    # Get intelligent context
    intelligent_context = get_conversation_intelligence(conversation_messages or [], client_id)

    # Get execution results memory for error recovery
    execution_memory = extract_execution_results_from_messages(conversation_messages or [])

    execution_rules = """
**ASSESSMENT PROTOCOL:**
1. **Native Tools Priority** - PowerShell cmdlets, WMI, CIM (Get-*, registry access)
2. **Alternative Methods** - System utilities when primary methods unavailable: certutil, wmic, net, reg, tasklist, netsh
3. **Adaptive Analysis** - Evaluate failures → Adjust technique → Retest with refined approach
4. **Intelligence Synthesis** - Correlate current findings with session history for comprehensive assessment
5. **Risk Classification** - Document operation type: "safe" (enumeration), "moderate" (detailed queries), "risky" (system modifications)

**Objective: Complete, accurate system intelligence for security evaluation.**"""

    # Combine all context sections
    sections = [base_prompt]
    if intelligent_context:
        sections.append(intelligent_context)
    if execution_memory:
        sections.append(execution_memory)
    sections.append(execution_rules)

    return '\n\n'.join(sections)

# Legacy compatibility function
def execute_powershell_command(client_id: str, command: str, db: Session, user: User) -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    return execute_dynamic_powershell(
        client_id=client_id,
        powershell_script=command,
        explanation="Legacy command execution",
        safety_assessment="moderate",
        db=db,
        user=user
    )

def get_tool_help() -> Dict[str, Any]:
    """Get help information about available tools - minimal for API documentation"""
    return {
        "available_tools": ["execute_powershell"],
        "description": "Dynamic PowerShell execution with intelligent context",
        "execution_philosophy": "PowerShell first, LOLBins as fallback, iterate on errors, learn from session",
        "safety_info": {
            "validation": "Blocks only catastrophic operations (format C:, system deletion)",
            "flexibility": "Maximum flexibility for legitimate admin tasks",
            "assessment_required": "safe/moderate/risky declaration required"
        }
    }