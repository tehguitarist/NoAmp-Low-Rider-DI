; TEMPLATE: rename this file and replace NoAmpLowRiderDI below with your plugin's product name. Inert
; until copied to a repo root and built.
;
; NoAmpLowRiderDI VST3 installer (NSIS). Windows has no AU format, so there's no plugin-type choice
; here — VST3 only, installed to the shared system VST3 folder.
;
; Build with (from repo root, after building NoAmpLowRiderDI_VST3):
;   makensis /DVERSION=0.1.0 /DARTEFACTS_DIR=build\NoAmpLowRiderDI_artefacts\Release\VST3 installer\windows\Pedal.nsi
;
; ARTEFACTS_DIR should point at the directory CONTAINING "NoAmp Low Rider DI.vst3" (i.e. the VST3
; release output folder), not the bundle itself. Note the bundle is named after PRODUCT_NAME
; ("NoAmp Low Rider DI", with spaces), not the CMake target name (NoAmpLowRiderDI).

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef ARTEFACTS_DIR
  !define ARTEFACTS_DIR "..\..\build\NoAmpLowRiderDI_artefacts\Release\VST3"
!endif

Name "NoAmpLowRiderDI"
OutFile "NoAmpLowRiderDI-Windows-v${VERSION}-Installer.exe"
InstallDir "$COMMONFILES64\VST3"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "NoAmpLowRiderDI VST3 Plugin" SecVST3
    SetOutPath "$INSTDIR\NoAmp Low Rider DI.vst3"
    File /r "${ARTEFACTS_DIR}\NoAmp Low Rider DI.vst3\*.*"

    WriteUninstaller "$INSTDIR\NoAmp Low Rider DI.vst3\Uninstall-NoAmpLowRiderDI.exe"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\NoAmpLowRiderDI" \
        "DisplayName" "NoAmpLowRiderDI VST3"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\NoAmpLowRiderDI" \
        "UninstallString" "$INSTDIR\NoAmp Low Rider DI.vst3\Uninstall-NoAmpLowRiderDI.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\NoAmpLowRiderDI" \
        "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\NoAmpLowRiderDI" \
        "Publisher" "Leigh Pierce"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR\NoAmp Low Rider DI.vst3"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\NoAmpLowRiderDI"
SectionEnd
