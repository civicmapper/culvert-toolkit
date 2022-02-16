@echo Installing Drain-It for ArcGIS Pro...

call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" config --add channels conda-forge
@REM call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" config --set channel_priority strict

@echo Cloning the base ArcGIS Pro Anaconda Python environment...

call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" create --clone arcgispro-py3 --name drainit-for-arcgispro --verbose

call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\activate.bat" drainit-for-arcgispro

@echo Updating packages...

call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" update –all

@echo ---
@echo Installing additional dependencies via conda...

for /f %%i in (setup\esri-cloned-requirements.txt) do "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" install --yes --verbose %%i

@echo ---
@echo Installing additional dependencies via pypi

for /f %%i in (setup\pip-requirements.txt) do pip install %%i

@echo Done!