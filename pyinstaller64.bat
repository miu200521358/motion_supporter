@echo off
rem --- 
rem ---  exe�𐶐�
rem --- 

rem ---  �J�����g�f�B���N�g�������s��ɕύX
cd /d %~dp0

cls

activate vmdsizing_cython_exe1 && pyinstaller --clean motion_supporter64.spec
