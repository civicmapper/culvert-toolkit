@echo Installing Drain-It for ArcGIS Pro...

call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" config --add channels conda-forge
@REM call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" config --set channel_priority strict

@echo Cloning the base ArcGIS Pro Anaconda Python environment...

call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" create --clone arcgispro-py3 --name drainit-for-arcgispro --verbose

call "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\activate.bat" drainit-for-arcgispro

@echo Installing additional dependencies...

for /f %%i in (setup\esri-cloned-requirements.txt) do "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" install --yes --verbose -c conda-forge esri%%i

@echo Done!