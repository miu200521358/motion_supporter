@echo off
rem --- 
rem ---  vmd�f�[�^�̃g���[�X���f����ϊ�
rem --- 

rem ---  �J�����g�f�B���N�g�������s��ɕύX
cd /d %~dp0

cls

src\setup.bat && activate vmdsizing_cython && python src\executor.py --out_log 1 --verbose 10 --is_saving 1

