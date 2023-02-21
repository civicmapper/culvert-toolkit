pytest -k TestNaaccETL -v -rxP -p no:faulthandler
python -m pytest -k test_naacc_data_ingest_from_fgdb_fc -v -rxP -p no:faulthandler
python -m pytest -k TestCapacityCalc -v -rxP -p no:faulthandler