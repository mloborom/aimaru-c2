# api/app/client_template_v2.py
"""
PSMCP v2 Client Template Generator
Generates PowerShell clients based on PSMCP_v2.ps1 with Phase 5 improvements
"""

def get_psmcp_v2_template() -> str:
    """
    Returns the PSMCP_v2.ps1 template content.
    This should be read from the actual file, but for now we'll return the core structure.
    """
    return """# =======================
#  PSMCP_v2.ps1  (Generated - Phase 5 Architecture)
#  Complete MCP PowerShell Client
#  - Updated for new API architecture with nginx proxy
#  - Enhanced authentication with JWT support
#  - HKDF → AES-256-CBC + HMAC-SHA256
#  - HTTPS support with self-signed certificates
#  - Improved error handling and logging
#  - Windows PowerShell 5.1 compatible
# =======================

[CmdletBinding()]
param(
  [Parameter(Mandatory=$false)] [string]$ServerBaseUrl = "{SERVER_URL}",
  [string]$ClientId = "{CLIENT_PREFIX}-" + $env:COMPUTERNAME,
  [ValidateSet('Poll','WebSocket')] [string]$Mode = 'Poll',

  # Auth methods
  [string]$ApiKey,
  [string]$EnrollToken,
  [string]$Username = "admin",
  [string]$Password = "admin",

  [int]$IntervalSec = {INTERVAL_SEC},
  [switch]$SkipTlsVerify{SKIP_TLS},
  [switch]$DebugMode{DEBUG_MODE}
)

# TLS Configuration
try {
  [Net.ServicePointManager]::SecurityProtocol =
    [Net.SecurityProtocolType]::Tls   -bor
    [Net.SecurityProtocolType]::Tls11 -bor
    [Net.SecurityProtocolType]::Tls12
} catch {
  Write-Warning "[mcp] Failed to set TLS protocols: $($_.Exception.Message)"
}

[System.Net.ServicePointManager]::CheckCertificateRevocationList = $false
[System.Net.ServicePointManager]::Expect100Continue = $false

if ($SkipTlsVerify) {
  [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
  Write-Warning "[mcp] TLS certificate validation is DISABLED for this process (dev only)."
}

# HKDF Implementation
function {FUNC_HKDF}([byte[]]$IKM, [byte[]]$Salt, [byte[]]$Info, [int]$Len=32){
  # Extract
  $hmac = New-Object System.Security.Cryptography.HMACSHA256
  $hmac.Key = $Salt
  $PRK = $hmac.ComputeHash($IKM)
  $hmac.Dispose()

  # Expand
  $out = New-Object byte[] $Len
  $T = $null
  $offset = 0
  $block = 0

  while ($offset -lt $Len) {
    $block++
    $lenT = if ($T) { $T.Length } else { 0 }
    $lenI = if ($Info) { $Info.Length } else { 0 }
    $input = New-Object byte[] ($lenT + $lenI + 1)

    if ($lenT -gt 0) { [Buffer]::BlockCopy($T, 0, $input, 0, $lenT) }
    if ($lenI -gt 0) { [Buffer]::BlockCopy($Info, 0, $input, $lenT, $lenI) }
    $input[$lenT + $lenI] = [byte]$block

    $h = New-Object System.Security.Cryptography.HMACSHA256
    $h.Key = $PRK
    $T = $h.ComputeHash($input)
    $h.Dispose()

    $take = [Math]::Min($Len - $offset, $T.Length)
    [Array]::Copy($T, 0, $out, $offset, $take)
    $offset += $take
  }

  return $out
}

# Global variables
{VAR_CRYPTO} = $null
{VAR_AUTH_HEADER} = $null
{VAR_AUTH_METHOD} = $null
{VAR_JWT_TOKEN} = $null
{VAR_JWT_EXPIRY} = $null

# Key Derivation
function {FUNC_DERIVE}([string]$ApiKey) {
  try {
    $ikm     = [Text.Encoding]::UTF8.GetBytes($ApiKey)
    $salt    = [Text.Encoding]::UTF8.GetBytes({STR_SALT})
    $encInfo = [Text.Encoding]::UTF8.GetBytes({STR_ENC})
    $macInfo = [Text.Encoding]::UTF8.GetBytes({STR_MAC})

    $encKey  = {FUNC_HKDF} -IKM $ikm -Salt $salt -Info $encInfo -Len 32
    $macKey  = {FUNC_HKDF} -IKM $ikm -Salt $salt -Info $macInfo -Len 32

    return @{ AES = $encKey; HMAC = $macKey }
  } catch {
    throw "Failed to derive crypto keys: $($_.Exception.Message)"
  }
}

# JWT Token Management
function {FUNC_TEST_JWT_EXPIRY} {
  if (-not {VAR_JWT_EXPIRY}) { return $false }
  $now = [DateTime]::UtcNow
  $buffer = [TimeSpan]::FromMinutes(5)
  return ($now.Add($buffer) -lt {VAR_JWT_EXPIRY})
}

function {FUNC_PARSE_JWT}([string]$Token) {
  try {
    $parts = $Token.Split('.')
    if ($parts.Length -ne 3) { return $null }
    $payload = $parts[1]
    $padding = 4 - ($payload.Length % 4)
    if ($padding -ne 4) { $payload += "=" * $padding }
    $bytes = [Convert]::FromBase64String($payload)
    $json = [Text.Encoding]::UTF8.GetString($bytes)
    $data = $json | ConvertFrom-Json
    if ($data.exp) {
      $epoch = [DateTime]::new(1970, 1, 1, 0, 0, 0, [DateTimeKind]::Utc)
      {VAR_JWT_EXPIRY} = $epoch.AddSeconds($data.exp)
    }
    return $data
  } catch {
    Write-Warning "[jwt] Failed to parse JWT: $($_.Exception.Message)"
    return $null
  }
}

function {FUNC_REFRESH_JWT} {
  if ({FUNC_TEST_JWT_EXPIRY}) {
    return $true
  }
  Write-Host "[mcp] JWT token expired or expiring soon, re-authenticating..." -ForegroundColor Yellow
  try {
    $token = {FUNC_GET_TOKEN} -ServerBaseUrl $ServerBaseUrl -ClientId $ClientId -Username $Username -Password $Password -EnrollToken $EnrollToken -ApiKey $ApiKey
    {VAR_JWT_TOKEN} = $token
    {VAR_AUTH_HEADER} = "Bearer " + $token
    {FUNC_PARSE_JWT} -Token $token | Out-Null
    Write-Host "[mcp] Token refreshed successfully" -ForegroundColor Green
    return $true
  } catch {
    Write-Warning "[mcp] Token refresh failed: $($_.Exception.Message)"
    return $false
  }
}

# Crypto Functions
function {FUNC_ENCRYPT}([string]$PlainText){
  if (-not {VAR_CRYPTO}) {
    throw "No crypto keys available. Client may need re-authentication."
  }
  try {
    $aes = [System.Security.Cryptography.Aes]::Create()
    $aes.KeySize = 256
    $aes.BlockSize = 128
    $aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aes.Key = {VAR_CRYPTO}.AES
    $aes.GenerateIV()
    $enc = $aes.CreateEncryptor()
    $plainBytes = [Text.Encoding]::UTF8.GetBytes($PlainText)
    $cipherBytes = $enc.TransformFinalBlock($plainBytes, 0, $plainBytes.Length)
    $all = New-Object byte[] ($aes.IV.Length + $cipherBytes.Length)
    [Array]::Copy($aes.IV, 0, $all, 0, 16)
    [Array]::Copy($cipherBytes, 0, $all, 16, $cipherBytes.Length)
    $aes.Dispose()
    $enc.Dispose()
    return [Convert]::ToBase64String($all)
  } catch {
    throw "Encryption failed: $($_.Exception.Message)"
  }
}

function {FUNC_DECRYPT}([string]$CipherTextB64){
  if (-not {VAR_CRYPTO}) {
    throw "No crypto keys available. Client may need re-authentication."
  }
  try {
    $raw = [Convert]::FromBase64String($CipherTextB64)
    if ($raw.Length -lt 17) { throw "Ciphertext too short (need IV + data)" }
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
    $aes.Key = {VAR_CRYPTO}.AES
    $aes.IV = $iv
    $dec = $aes.CreateDecryptor()
    $plainBytes = $dec.TransformFinalBlock($ct, 0, $ct.Length)
    $aes.Dispose()
    $dec.Dispose()
    return [Text.Encoding]::UTF8.GetString($plainBytes)
  } catch {
    throw "Decryption failed: $($_.Exception.Message)"
  }
}

function {FUNC_GET_HMAC}([string]$Message){
  if (-not {VAR_CRYPTO}) { throw "No crypto keys available for HMAC" }
  try {
    $msgBytes = [Text.Encoding]::UTF8.GetBytes($Message)
    $h = New-Object System.Security.Cryptography.HMACSHA256
    $h.Key = {VAR_CRYPTO}.HMAC
    $mac = $h.ComputeHash($msgBytes)
    $h.Dispose()
    return [Convert]::ToBase64String($mac)
  } catch {
    throw "HMAC generation failed: $($_.Exception.Message)"
  }
}

function {FUNC_TEST_HMAC}([string]$Message, [string]$Kid, [string]$SigB64){
  if (-not {VAR_CRYPTO}) { return $false }
  if ($Kid -ne 'v1') { return $false }
  try {
    $msgRaw = $Message
    $msgLF  = $Message -replace "`r`n","`n"
    $msgCRLF= $msgLF   -replace "`n","`r`n"
    $expRaw  = {FUNC_GET_HMAC} -Message $msgRaw
    if ($expRaw -eq $SigB64) { return $true }
    $expLF   = {FUNC_GET_HMAC} -Message $msgLF
    if ($expLF -eq $SigB64) { return $true }
    $expCRLF = {FUNC_GET_HMAC} -Message $msgCRLF
    if ($expCRLF -eq $SigB64) { return $true }
    return $false
  } catch {
    return $false
  }
}

# REST API Helper
function {FUNC_INVOKE_API} {
  param(
    [Parameter(Mandatory)][ValidateSet('GET','POST','PUT','DELETE')] [string]$Method,
    [Parameter(Mandatory)][string]$Path,
    [hashtable]$Headers,
    [object]$Body
  )
  $uri = ($ServerBaseUrl.TrimEnd('/')) + $Path
  $h = @{}
  if ($Headers) { $Headers.GetEnumerator() | ForEach-Object { $h[$_.Key] = $_.Value } }
  try {
    if ($Method -eq 'GET') {
      return Invoke-RestMethod -Uri $uri -Headers $h -Method Get -ErrorAction Stop
    } else {
      if (-not $h.ContainsKey('Content-Type')) { $h['Content-Type'] = 'application/json' }
      $json = if ($null -ne $Body) { ($Body | ConvertTo-Json -Depth 10 -Compress) } else { '{}' }
      return Invoke-RestMethod -Uri $uri -Headers $h -Method $Method -Body $json -ErrorAction Stop
    }
  } catch {
    Write-Warning "[api] $Method $uri failed"
    throw "API $Method $uri failed: $($_.Exception.Message)"
  }
}

# Token Acquisition
function {FUNC_GET_TOKEN} {
  param(
    [Parameter(Mandatory)][string]$ServerBaseUrl,
    [Parameter(Mandatory)][string]$ClientId,
    [string]$Username,
    [string]$Password,
    [string]$EnrollToken,
    [string]$ApiKey
  )
  if ($ApiKey) {
    try {
      $headers = @{
        "Authorization" = "ApiKey $ApiKey"
        "X-MCP-ClientId" = $ClientId
      }
      $body = @{ api_key = $ApiKey; client_id = $ClientId }
      $res = {FUNC_INVOKE_API} -Method POST -Path "/api/auth/token-by-apikey" -Headers $headers -Body $body
      if ($res.access_token) {
        {VAR_AUTH_METHOD} = "ApiKey"
        return $res.access_token
      }
      throw "API key exchange returned no access_token"
    } catch {
      Write-Warning "[mcp] API key auth failed: $($_.Exception.Message)"
      throw $_
    }
  }
  if ($EnrollToken) {
    try {
      $path = "/api/auth/token?enroll=" + [Uri]::EscapeDataString($EnrollToken) + "&client_id=" + [Uri]::EscapeDataString($ClientId)
      $res = {FUNC_INVOKE_API} -Method POST -Path $path
      if ($res.access_token) {
        {VAR_AUTH_METHOD} = "EnrollToken"
        return $res.access_token
      }
      throw "Enroll exchange returned no access_token"
    } catch {
      Write-Warning "[mcp] Enroll token auth failed: $($_.Exception.Message)"
      throw $_
    }
  }
  if ($Username -and $Password) {
    try {
      $res = {FUNC_INVOKE_API} -Method POST -Path "/api/auth/token" -Body @{ username=$Username; password=$Password }
      if ($res.access_token) {
        {VAR_AUTH_METHOD} = "UsernamePassword"
        return $res.access_token
      }
      throw "Auth returned no access_token"
    } catch {
      Write-Warning "[mcp] Username/password auth failed: $($_.Exception.Message)"
      throw $_
    }
  }
  throw "Choose one auth method: -ApiKey OR -EnrollToken OR -Username/-Password."
}

# Command Execution
function {FUNC_INVOKE_INSTRUCTION}([string]$CommandText){
  try {
    $Error.Clear()
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Stop'
    $result = Invoke-Expression -Command $CommandText | Out-String -Width 2000
    $ErrorActionPreference = $old
    if (-not $result) { $result = "<no output>" }
    return @{ ok=$true; output=$result }
  } catch {
    return @{ ok=$false; output=("ERROR: " + $_.Exception.Message) }
  }
}

# System Information
function {FUNC_GET_SYSINFO} {
  $os = Get-WmiObject Win32_OperatingSystem
  $cpu = Get-WmiObject Win32_Processor | Select-Object -First 1
  $mem = Get-WmiObject Win32_ComputerSystem
  return @{
    hostname = $env:COMPUTERNAME
    os_name = $os.Caption
    os_version = $os.Version
    cpu = $cpu.Name
    cpu_cores = $cpu.NumberOfCores
    memory_gb = [Math]::Round($mem.TotalPhysicalMemory / 1GB, 2)
    username = $env:USERNAME
    domain = $env:USERDOMAIN
    powershell_version = $PSVersionTable.PSVersion.ToString()
  }
}

# Main Script
Write-Host ""
Write-Host "=== MCP PowerShell Client v2 ===" -ForegroundColor Green
Write-Host ""
Write-Host "[mcp] ClientId: $ClientId" -ForegroundColor Cyan
Write-Host "[mcp] Server: $ServerBaseUrl" -ForegroundColor Cyan
Write-Host ""

try {
  Write-Host "[mcp] Authenticating..." -ForegroundColor Yellow
  $token = {FUNC_GET_TOKEN} -ServerBaseUrl $ServerBaseUrl -ClientId $ClientId -Username $Username -Password $Password -EnrollToken $EnrollToken -ApiKey $ApiKey
  {VAR_JWT_TOKEN} = $token
  {VAR_AUTH_HEADER} = "Bearer $token"
  {FUNC_PARSE_JWT} -Token $token | Out-Null

  if ({VAR_AUTH_METHOD} -eq "ApiKey" -and $ApiKey) {
    Write-Host "[mcp] Deriving encryption keys..." -ForegroundColor Yellow
    {VAR_CRYPTO} = {FUNC_DERIVE} -ApiKey $ApiKey
    Write-Host "[mcp] Encryption keys derived" -ForegroundColor Green
  }

  try {
    $sysInfo = {FUNC_GET_SYSINFO}
    $heartbeatBody = @{ client_id = $ClientId; system_info = $sysInfo }
    $null = {FUNC_INVOKE_API} -Method POST -Path "/api/clients/heartbeat" -Headers @{ Authorization = {VAR_AUTH_HEADER} } -Body $heartbeatBody
    Write-Host "[mcp] Heartbeat sent successfully" -ForegroundColor Green
  } catch {
    Write-Warning "[mcp] Heartbeat failed: $($_.Exception.Message)"
  }

  Write-Host ""
  Write-Host "[mcp] [OK] Authentication complete. Ready for polling." -ForegroundColor Green
  Write-Host ""
} catch {
  Write-Error "[mcp] Authentication failed: $($_.Exception.Message)"
  exit 1
}

# Poll Loop
if ($Mode -eq 'Poll') {
  Write-Host "[mcp] Starting POLL loop..." -ForegroundColor Cyan
  Write-Host "[mcp] Polling interval: $IntervalSec seconds" -ForegroundColor Cyan
  Write-Host ""

  $pollCount = 0
  $lastHeartbeat = [DateTime]::UtcNow
  $heartbeatInterval = [TimeSpan]::FromMinutes(5)

  while ($true) {
    try {
      if (-not ({FUNC_REFRESH_JWT})) {
        Write-Error "[mcp] Unable to refresh JWT token. Exiting."
        exit 1
      }

      $now = [DateTime]::UtcNow
      if (($now - $lastHeartbeat) -gt $heartbeatInterval) {
        try {
          $null = {FUNC_INVOKE_API} -Method POST -Path "/api/clients/heartbeat" -Headers @{ Authorization = {VAR_AUTH_HEADER} } -Body @{ client_id = $ClientId }
          $lastHeartbeat = $now
        } catch {
          Write-Warning "[mcp] Periodic heartbeat failed"
        }
      }

      $pollCount++
      $headers = @{ Authorization = {VAR_AUTH_HEADER} }
      $path = "/api/get-instruction?client_id=" + [Uri]::EscapeDataString($ClientId)
      $uri = ($ServerBaseUrl.TrimEnd('/')) + $path

      $wr = Invoke-WebRequest -Uri $uri -Headers $headers -Method Get -ErrorAction Stop

      if ($wr.StatusCode -eq 204) {
        Start-Sleep -Seconds $IntervalSec
        continue
      }

      $resp = $wr.Content | ConvertFrom-Json
      $InstructionId = [string]$resp.id
      $kid = [string]$resp.kid
      $sig = [string]$resp.sig
      $enc = [string]$resp.encryptedCommand

      Write-Host "[mcp] >> Received instruction $InstructionId" -ForegroundColor Cyan

      $cmd = $null
      try {
        $cmd = {FUNC_DECRYPT} -CipherTextB64 $enc
      } catch {
        Write-Warning "[mcp] Decrypt failed for instruction $InstructionId"
        Start-Sleep -Seconds $IntervalSec
        continue
      }

      if (-not ({FUNC_TEST_HMAC} -Message $cmd -Kid $kid -SigB64 $sig)) {
        Write-Warning "[mcp] [X] HMAC verification FAILED for instruction $InstructionId"
        Start-Sleep -Seconds $IntervalSec
        continue
      }

      Write-Host "[mcp] >> Executing instruction: $cmd" -ForegroundColor Yellow

      $exec = {FUNC_INVOKE_INSTRUCTION} -CommandText $cmd
      $payloadText = if ($exec.ok) { $exec.output } else { $exec.output }

      if ($exec.ok) {
        Write-Host "[mcp] [OK] Command executed successfully" -ForegroundColor Green
      } else {
        Write-Warning "[mcp] [ERROR] Command execution failed"
      }

      try {
        $encResult = {FUNC_ENCRYPT} -PlainText $payloadText
        $body = @{ id = $InstructionId; client_id = $ClientId; encryptedResult = $encResult }
        $null = {FUNC_INVOKE_API} -Method POST -Path "/api/send-result" -Headers @{ Authorization = {VAR_AUTH_HEADER} } -Body $body
        Write-Host "[mcp] << Result sent for instruction $InstructionId" -ForegroundColor Green
      } catch {
        Write-Warning "[mcp] Failed to send result for $InstructionId"
      }

      Start-Sleep -Seconds 1
    } catch {
      Write-Warning "[mcp] Poll error: $($_.Exception.Message)"
      Start-Sleep -Seconds $IntervalSec
    }
  }
} else {
  Write-Error "[mcp] WebSocket mode not implemented. Use -Mode Poll."
  exit 1
}
"""
