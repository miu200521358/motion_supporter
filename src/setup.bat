@echo off
cls

cd /d %~dp0

rem -- �s�v���t�@�C���p
rem kernprof -l setup.py build_ext --inplace


rem -- �ʏ�p
python setup.py build_ext --inplace

cd ..
