:: Limpar cache do PyInstaller
rmdir /s /q build
rmdir /s /q dist
rmdir /s /q __pycache__
del /q *.spec

:: Limpar cache Python
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
del /s /q *.pyc

python build_installer.py


:: e7e23197867fb398c6483e79627ce40e65e392313220752bdc0cba610666e512 - 5KDS-W5YY-ND1W-ZQTH-SYE1

