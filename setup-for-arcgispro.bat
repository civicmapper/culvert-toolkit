@echo Installing Drain-It for ArcGIS Pro...

@echo Cloning the base ArcGIS Pro Anaconda Python environment...

call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" create --clone arcgispro-py3 --name drainit-for-arcgispro --verbose

call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\activate.bat" drainit-for-arcgispro

@echo Installing additional dependencies...

@REM call conda env update -n drainit-for-arcgispro -f cfg/esri-cloned.yml --verbose
for /f %%i in (cfg\esri-cloned-requirements.txt) do conda install --yes --verbose %%i

@echo Done!