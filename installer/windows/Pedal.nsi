; TEMPLATE: rename this file and replace <Pedal> below with your plugin's product name. Inert
; until copied to a repo root and built.
;
; <Pedal> VST3 installer (NSIS). Windows has no AU format, so there's no plugin-type choice
; here — VST3 only, installed to the shared system VST3 folder.
;
; Build with (from repo root, after building <Pedal>_VST3):
;   makensis /DVERSION=0.1.0 /DARTEFACTS_DIR=build\<Pedal>_artefacts\Release\VST3 installer\windows\Pedal.nsi
;
; ARTEFACTS_DIR should point at the directory CONTAINING <Pedal>.vst3 (i.e. the VST3 release
; output folder), not <Pedal>.vst3 itself.

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef ARTEFACTS_DIR
  !define ARTEFACTS_DIR "..\..\build\<Pedal>_artefacts\Release\VST3"
!endif

Name "<Pedal>"
OutFile "<Pedal>-Windows-v${VERSION}-Installer.exe"
InstallDir "$COMMONFILES64\VST3"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "<Pedal> VST3 Plugin" SecVST3
    SetOutPath "$INSTDIR\<Pedal>.vst3"
    File /r "${ARTEFACTS_DIR}\<Pedal>.vst3\*.*"

    WriteUninstaller "$INSTDIR\<Pedal>.vst3\Uninstall-<Pedal>.exe"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\<Pedal>" \
        "DisplayName" "<Pedal> VST3"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\<Pedal>" \
        "UninstallString" "$INSTDIR\<Pedal>.vst3\Uninstall-<Pedal>.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\<Pedal>" \
        "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\<Pedal>" \
        "Publisher" "<You>"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR\<Pedal>.vst3"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\<Pedal>"
SectionEnd
