; WinClaw NSIS 安装程序脚本
; 使用 NSIS 3.x 编译
; 命令: makensis installer.nsi

;--------------------------------
; 基本定义

!define PRODUCT_NAME "WinClaw"
!define PRODUCT_VERSION "0.1.0"
!define PRODUCT_PUBLISHER "WinClaw"
!define PRODUCT_WEB_SITE "https://github.com/your-org/winclaw"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\winclaw.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

;--------------------------------
; 现代 UI

!include "MUI2.nsh"
!include "FileFunc.nsh"

; MUI 设置
!define MUI_ABORTWARNING
!define MUI_ICON "resources\icons\winclaw.ico"
!define MUI_UNICON "resources\icons\winclaw.ico"

; 欢迎页面
!insertmacro MUI_PAGE_WELCOME
; 许可协议页面（可选）
; !insertmacro MUI_PAGE_LICENSE "LICENSE"
; 安装目录页面
!insertmacro MUI_PAGE_DIRECTORY
; 安装文件页面
!insertmacro MUI_PAGE_INSTFILES
; 完成页面
!define MUI_FINISHPAGE_RUN "$INSTDIR\winclaw.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 ${PRODUCT_NAME}"
!insertmacro MUI_PAGE_FINISH

; 卸载页面
!insertmacro MUI_UNPAGE_INSTFILES

; 语言
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; 安装程序属性

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "WinClawSetup-${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show
RequestExecutionLevel admin

;--------------------------------
; 安装区段

Section "主程序" SEC01
  SetOutPath "$INSTDIR"
  SetOverwrite on
  
  ; 复制主程序和依赖
  File /r "dist\WinClaw\*.*"
  
  ; 创建开始菜单快捷方式
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\winclaw.exe"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\卸载 ${PRODUCT_NAME}.lnk" "$INSTDIR\uninstall.exe"
  
  ; 创建桌面快捷方式（可选）
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\winclaw.exe"
SectionEnd

Section "开机自启动" SEC02
  ; 添加到开机启动项（可选）
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" "$INSTDIR\winclaw.exe --minimized"
SectionEnd

Section -Post
  ; 写入卸载程序
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
  ; 写入注册表信息
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\winclaw.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\winclaw.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  
  ; 获取安装大小
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

;--------------------------------
; 组件描述

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC01} "安装 ${PRODUCT_NAME} 主程序和必需文件。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC02} "开机时自动启动 ${PRODUCT_NAME}（可在设置中关闭）。"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
; 卸载区段

Section Uninstall
  ; 关闭正在运行的程序
  nsExec::ExecToLog 'taskkill /F /IM winclaw.exe'
  
  ; 删除开机启动项
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
  
  ; 删除文件和目录
  RMDir /r "$INSTDIR"
  
  ; 删除开始菜单快捷方式
  RMDir /r "$SMPROGRAMS\${PRODUCT_NAME}"
  
  ; 删除桌面快捷方式
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  
  ; 删除注册表项
  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
  DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
  
  ; 清理用户数据（可选，询问用户）
  MessageBox MB_YESNO "是否删除用户数据和配置文件？" IDNO skip_userdata
    RMDir /r "$APPDATA\${PRODUCT_NAME}"
    RMDir /r "$LOCALAPPDATA\${PRODUCT_NAME}"
  skip_userdata:
  
  SetAutoClose true
SectionEnd

;--------------------------------
; 安装前检查

Function .onInit
  ; 检查是否已安装
  ReadRegStr $R0 ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString"
  StrCmp $R0 "" done
  
  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
  "${PRODUCT_NAME} 已安装。$\n$\n点击「确定」卸载旧版本后继续安装，或点击「取消」取消安装。" \
  IDOK uninst
  Abort
  
uninst:
  ClearErrors
  ExecWait '$R0 /S'
  
done:
FunctionEnd

;--------------------------------
; 卸载前检查

Function un.onInit
  MessageBox MB_ICONQUESTION|MB_YESNO "确定要卸载 ${PRODUCT_NAME}？" IDYES +2
  Abort
FunctionEnd

Function un.onUninstSuccess
  MessageBox MB_ICONINFORMATION "${PRODUCT_NAME} 已成功卸载。"
FunctionEnd
