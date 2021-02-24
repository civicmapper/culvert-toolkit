# standard library
import csv
import json
from pathlib import Path
from copy import deepcopy
from io import BytesIO
import zipfile

from dataclasses import asdict

# dependencies
import petl as etl
import requests
from tqdm import tqdm

# application
from ..models import RainfallRasterConfig, RainfallRaster, RainfallRasterConfigSchema
from ..config import (
    QP_PREFIX,
    NOAA_RAINFALL_REGION_LOOKUP,
    FREQUENCIES
)

# -------------------------------------------------------------------
# PRECIPTATION DATA TABLES


def extract_noaa_precip_table(
    precip_table,
    rainfall_adjustment=1,
    frequency_min=min(FREQUENCIES),
    frequency_max=max(FREQUENCIES),
    conversion_factor=2.54,
    desc_field="by duration for ARI (years):",
    duration_val="24-hr:",
    ):
    """
    Extract, Transform, and Load data from a NOAA PRECIPITATION FREQUENCY
    ESTIMATES matrix (in a csv) into an array used by the runoff calculator.

    Required Inputs:
        - precip_table: NOAA PRECIPITATION FREQUENCY ESTIMATES csv, in inches.
    Optional Inputs:
        - rainfall_adjustment: multipler to adjust for future rainfall
            conditions. defaults to 1.
        - frequency_min: the min. annual frequency to be returned. Default: 1
        - frequency_max: the max. annual frequency to be returned. Default: 500
        - conversion_factor: apply to rainfall values. Default: 2.54
            (convert inches to centimeters).
        - desc_field: exact field name from NOAA table in first column.
            Defaults to "by duration for ARI (years):". Used for selecting
            data.
        - duration_val: exact row value in the desc_field from NOAA table that
            contains the duration of interest. Defaults to "24-hr:". Used for
            selecting data.
    Outputs:
        - precip_dict: a dictionary containing 24-hour duration estimate for
        frequencies 1,2,5,10,25,50,100,200,500 year storm events (by default)
    """
    # load the csv table, skip the file header information, extract rows we need
    t1 = etl.fromcsv(precip_table).skip(13).rowslice(0, 19)
    # grab raw data from the row containing the x-hour duration event info
    t2 = etl.select(t1, desc_field, lambda v: v == duration_val).cutout(desc_field)
    # generate a new header with only columns within frequency min/max
    h = tuple(
        [
            i
            for i in list(etl.header(t2))
            if (int(i) >= frequency_min and int(i) <= frequency_max)
        ]
    )
    # for events within freq range, convert to cm, adjust for future rainfall
    t3 = etl.cut(t2, h).convertall(
        lambda v: round(float(v) * conversion_factor * rainfall_adjustment, 2)
    )

    # convert to a dictionary, keyed by the frequency
    precips = {
        "{0}{1}".format(QP_PREFIX, k): v for k, v in list(etl.dicts(t3))[0].items()
    }

    return precips


# -------------------------------------------------------------------
# PRECIPTATION DATA RASTERS


def retrieve_noaa_rainfall_rasters(
    out_folder,
    out_file_name="rainfall_rasters_config",
    study="orb",
    url="https://hdsc.nws.noaa.gov/hdsc/pfds/newzip.php",
    ulm="a",
    ser="pds",
    dur="24h",
    frequencies=FREQUENCIES,
    ) -> RainfallRasterConfig:
    """Download NOAA rainfall rasters from the Hydrometeorological Design Studies
    Center Precipitation Frequency Data Server (PFDS).

    Manually download this data through https://hdsc.nws.noaa.gov/hdsc/pfds/pfds_gis.html
    See "options from the NOAA page" below to see the origin of the these kwargs.

    :param out_folder: output folder for the rasters. rasters use the CRS `GCS North America US and Territories NAD 83`
    :type out_folder: string, Path object
    :param study: study region [orb, ne, sa, se, pr, pi, sw, ak, mw, tx], defaults to "orb" (ohio river basin).
        Note that the values found in NOAA_RAINFALL_REGION_LOOKUP will also work here.
    :type study: str, optional
    :param url: URL for the PFDS download server, defaults to "https://hdsc.nws.noaa.gov/hdsc/pfds/newzip.php"
    :type url: str, optional
    :param ulm: Type, defaults to "a"
    :type ulm: str, optional
    :param ser: [pds, ads], defaults to "pds" (partial duration series)
    :type ser: str, optional
    :param dur: duration, defaults to "24h"
    :type dur: str, optional
    :param frequencies: rainfall event frequencies to download, defaults to [1,2,5,10,25,50,100,200,500,1000]
    :type frequencies: list, optional
    :raises Exception: [description]
    :return: a dataclass with properties indicating the location of downloaded files + useful descriptors
    :rtype: RainfallRasterConfig

    -----------------------------
    options from the NOAA page:

    study:
    <option value="sa">1: Semiarid Southwest</option>
    <option value="orb">2: Ohio River Basin and Surrounding States</option>
    <option value="pr">3: Puerto Rico and the U.S. Virgin Islands</option>
    <option value="hi">4: Hawaiian Islands</option>
    <option value="pi">5: Selected Pacific Islands</option>
    <option value="sw">6: California</option>
    <option value="ak">7: Alaska</option>
    <option value="mw">8: Midwestern States</option>
    <option value="se">9: Southeastern States</option>
    <option value="ne">10: Northeastern States</option>
    <option value="tx">11: Texas</option>

    ulm:
    <option value="a">Precipitation frequency estimates</option>
    <option value="au">Upper confidence limits</option>
    <option value="al">Lower confidence limits</option>

    ser:
    <option value="pds">Partial duration series</option>
    <option value="ams">Annual maximum series</option>

    freq:
    <option value="1yr">1-year</option>
    <option value="2yr">2-year</option>
    <option value="5yr">5-year</option>
    <option value="10yr">10-year</option>
    <option value="25yr">25-year</option>
    <option value="50yr">50-year</option>
    <option value="100yr">100-year</option>
    <option value="200yr">200-year</option>
    <option value="500yr">500-year</option>
    <option value="1000yr">1000-year</option>

    (NOTE: our current tool is limited to <= 500 year freq)

    dur:
    <option value="05m">5-minute</option>
    <option value="10m">10-minute</option>
    <option value="15m">15-minute</option>
    <option value="30m">30-minute</option>
    <option value="60m">60-minute</option>
    <option value="02h">2-hour</option>
    <option value="03h">3-hour</option>
    <option value="06h">6-hour</option>
    <option value="12h">12-hour</option>
    <option value="24h">24-hour</option>
    <option value="48h">2-day</option>
    <option value="03d">3-day</option>
    <option value="04d">4-day</option>
    <option value="07d">7-day</option>
    <option value="10d">10-day</option>
    <option value="20d">20-day</option>
    <option value="30d">30-day</option>
    <option value="45d">45-day</option>
    <option value="60d">60-day</option>

    (NOTE: the TR-55 method only works with the 24-hour duration)

    """

    if study in NOAA_RAINFALL_REGION_LOOKUP.keys():
        study = study
    elif study in NOAA_RAINFALL_REGION_LOOKUP.values():
        try:
            study = next(
                key
                for key, value in NOAA_RAINFALL_REGION_LOOKUP.items()
                if value == study
            )
        except:
            print(
                "Download failed. Study area must by one of [orb, ne, sa, se, pr, pi, sw, ak, mw, tx, hi]"
            )
            raise Exception
    else:
        print(
            "Download failed. Study area must by one of [orb, ne, sa, se, pr, pi, sw, ak, mw, tx, hi]"
        )
        raise Exception

    # assemble post_kwargs: arguments used for the download request (sent as form data in the POST request body),
    # defaults to {"study":"orb","ulm":"a","ser":"pds","dur":"24h"}
    post_kwargs = dict(study=study, ulm=ulm, ser=ser, dur=dur)

    c = RainfallRasterConfig(root=out_folder)
    out_path = Path(out_folder)

    for freq in tqdm(frequencies):

        # assemble the kwargs for the request
        data = deepcopy(post_kwargs)
        data["freq"] = "{}yr".format(freq)

        # make the request
        r = requests.post(url, data=data, stream=True)
        if r.ok:
            # extract the response to the output folder
            z = zipfile.ZipFile(BytesIO(r.content))
            z.extractall(c.path)

            # list files in the zip folder
            files_from_zip = z.NameToInfo.keys()

            # create a lookup table that will help us find these later
            for f in files_from_zip:
                p = out_path / f
                ext = p.suffix
                c.rasters.append(
                    RainfallRaster(f, freq, ext)
                )
        else:
            print("Download failed for {0} ({1})".format(data["freq"], data))
            raise Exception

    out_full_path = out_path / "{0}_{1}.json".format(out_file_name, study)

    with open(out_full_path, 'w') as fp:
        json.dump(
            RainfallRasterConfigSchema().dump(asdict(c)),
            fp
        )

    return c

