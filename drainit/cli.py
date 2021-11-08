"""cli.py

command line interface for drain-it, built with click

WIP

"""
# import click
# from workflows import RainfallDataGetter

# click.command()
# click.option('--name', default="rainfall_rasters_config.json")
# def get_rainfall_rasters(aoi_geo, out_folder, name):
#     """Acquire rainfall rasters for an area of interest from NOAA

#     Args:
#         aoi_geo (str): path to geodata containing points or area of interest
#         out_folder (str): folder path where outputs will be saved
#         name (str, optional): name of output raster reference file. Defaults to "rainfall_rasters_config.json".
#     """ 
#     return RainfallDataGetter(
#         aoi_geo=aoi_geo, 
#         out_folder=out_folder, 
#         out_file_name=name
#     )


# @click.group()
# def drainit():
#     pass
# drainit.add_command(get_rainfall_rasters)


# if __name__ == '__main__':
#     drainit()