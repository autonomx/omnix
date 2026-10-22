; Omnix's uninstaller keeps the user's data (%LOCALAPPDATA%\OmnixDesktop: database, settings, logs) and downloaded
; runtimes and models (the "packs" folder in the install folder) unless the user chooses to remove them (desktop roadmap
; §4.9, DT-6.1).
!macro customUnInstall
  ${ifNot} ${isUpdated}
    MessageBox MB_YESNO|MB_ICONQUESTION "Also remove your Omnix data and downloaded models (database, settings, logs, runtimes and models)?$\r$\n$\r$\nChoose No to keep it for a later install." /SD IDNO IDNO keepData
      RMDir /r "$INSTDIR\packs"
      ; A packs folder moved to another drive (Settings, Models) is named in packs-location.txt; it is removed only
      ; when it is the "OmnixPacks" folder the move created, never any other folder the file might name.
      ClearErrors
      FileOpen $0 "$LOCALAPPDATA\OmnixDesktop\packs-location.txt" r
      ${ifNot} ${Errors}
        FileReadUTF16LE $0 $1
        FileClose $0
        StrCpy $2 $1 "" -11
        ${if} $2 == "\OmnixPacks"
          RMDir /r "$1"
        ${endIf}
      ${endIf}
      RMDir /r "$LOCALAPPDATA\OmnixDesktop"
    keepData:
  ${endIf}
  ; The app registers itself to start at login; remove that entry with the app.
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "com.autonomx.omnix"
!macroend

; The app's files go; the downloaded runtimes and models ("packs", kept unless customUnInstall removed them) stay, on an
; update and on an uninstall that keeps the data. The install folder itself goes once it is empty.
!macro customRemoveFiles
  SetOutPath $TEMP
  FindFirst $0 $1 "$INSTDIR\*.*"
  ${doWhile} $1 != ""
    ${if} $1 != "."
    ${andIf} $1 != ".."
    ${andIf} $1 != "packs"
      ${if} ${FileExists} "$INSTDIR\$1\*.*"
        RMDir /r "$INSTDIR\$1"
      ${else}
        Delete "$INSTDIR\$1"
      ${endIf}
    ${endIf}
    FindNext $0 $1
  ${loop}
  FindClose $0
  RMDir "$INSTDIR"
!macroend

; An update runs the uninstaller of the version already installed, and one older than customRemoveFiles deletes the
; whole install folder. So the packs wait beside it while the old version is removed and come back once the new files
; are in (customInstall); an install that stops in between finds them there the next time.
!ifndef BUILD_UNINSTALLER
  !macro keepPacksAside
    ${if} ${FileExists} "$INSTDIR\packs\*.*"
    ${andIfNot} ${FileExists} "$INSTDIR.packs-update\*.*"
      ClearErrors
      Rename "$INSTDIR\packs" "$INSTDIR.packs-update"
      ${if} ${Errors}
        ; Never let the old uninstaller run with the packs still inside the folder it removes.
        MessageBox MB_OK|MB_ICONSTOP "Omnix's downloaded models in $INSTDIR\packs are in use, so the update cannot continue. Close any program using that folder and run the installer again." /SD IDOK
        Quit
      ${endIf}
    ${endIf}
  !macroend

  !macro customInstall
    ${if} ${FileExists} "$INSTDIR.packs-update\*.*"
    ${andIfNot} ${FileExists} "$INSTDIR\packs\*.*"
      Rename "$INSTDIR.packs-update" "$INSTDIR\packs"
    ${endIf}
  !macroend
!endif

; The install folder's length: NSIS cannot remove a file whose path is over 260 characters, and the deepest staged
; file is up to 140 characters below resources\runtime\ (MAX_RELATIVE_PATH in desktop/staging/stage.py), so a longer
; folder would install but never update or uninstall cleanly. The directory page keeps Next disabled past 100 characters.
!ifndef BUILD_UNINSTALLER
  Function .onVerifyInstDir
    ; This file is included before LogicLib, so no ${if} outside the macros: up to 100 skips the Abort.
    StrLen $0 $INSTDIR
    IntCmp $0 100 +2 +2
      Abort
  FunctionEnd
!endif

; Before files are replaced or removed (install, update, uninstall): electron-builder's own check force-kills every
; process in the install folder after about a second, PostgreSQL included, and the uninstall then races their file
; handles. Instead ask Omnix to quit (`--quit`: it stops the backend and shuts PostgreSQL down cleanly), wait
; for every process started from the install folder to exit, and force them only after a minute.
;
; The install folder reaches PowerShell through an environment variable, never inside its command text, so a folder
; with an apostrophe (C:\Users\O'Brien\...) cannot break the check. Exit code 3 alone means "nothing running"; any
; other result, a PowerShell failure included, is treated as still running.
!macro customCheckAppRunning
  System::Call 'Kernel32::SetEnvironmentVariable(t "OMNIXDESKTOP_INSTDIR", t "$INSTDIR\")i'
  StrCpy $R8 `"$PowerShellPath" -NoProfile -NonInteractive -C "if (@(Get-CimInstance -ClassName Win32_Process | ? {$$_.Path -and $$_.Path.StartsWith($$env:OMNIXDESKTOP_INSTDIR, 'CurrentCultureIgnoreCase')}).Count -gt 0) { exit 0 } else { exit 3 }"`
  nsExec::Exec $R8
  Pop $R0
  ${if} $R0 != 3
    DetailPrint "$(appClosing)"
    ${if} ${FileExists} "$INSTDIR\${APP_EXECUTABLE_FILENAME}"
      Exec `"$INSTDIR\${APP_EXECUTABLE_FILENAME}" --quit`
    ${endIf}
    StrCpy $R1 0
    ${doWhile} $R0 != 3
      ${if} $R1 >= 60
        ${exitDo}
      ${endIf}
      Sleep 1000
      IntOp $R1 $R1 + 1
      nsExec::Exec $R8
      Pop $R0
    ${loop}
    ${if} $R0 != 3
      DetailPrint `"${PRODUCT_NAME}" did not quit within a minute; closing it.`
      nsExec::Exec `"$PowerShellPath" -NoProfile -NonInteractive -C "Get-CimInstance -ClassName Win32_Process | ? {$$_.Path -and $$_.Path.StartsWith($$env:OMNIXDESKTOP_INSTDIR, 'CurrentCultureIgnoreCase')} | % { Stop-Process -Id $$_.ProcessId -Force }"`
      Sleep 2000
    ${endIf}
  ${endIf}
  !ifndef BUILD_UNINSTALLER
    !insertmacro keepPacksAside
  !endif
!macroend
