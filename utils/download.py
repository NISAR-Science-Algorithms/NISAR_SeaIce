import getpass
import netrc
import os
import zipfile
from pathlib import Path
from typing import List, Optional

import requests
from tqdm.notebook import tqdm


def get_earthdata_credentials():
    """
    Get Earthdata credentials either from ~/.netrc or by prompting the user.
    Returns (username, password).
    """
    try:
        info = netrc.netrc()
        # The machine name for ASF Earthdata
        auth = info.authenticators("urs.earthdata.nasa.gov")
        if auth:
            username, _, password = auth
            return username, password
    except FileNotFoundError:
        pass
    except netrc.NetrcParseError:
        pass

    # If .netrc is missing or incomplete, prompt user
    username = input("Enter your Earthdata username: ")
    password = getpass.getpass("Enter your Earthdata password: ")
    return username, password


def download_asf_pair_authenticated(pairs_df, gdf_results, pair_index,
                                    output_dir="asf_pair_downloads",
                                    overwrite=False):
    """
    Download a pair of ASF granules using Earthdata credentials from ~/.netrc or interactive prompt.

    Returns paths as PosixPath objects.
    """
    username, password = get_earthdata_credentials()

    os.makedirs(output_dir, exist_ok=True)
    output_dir = Path(output_dir)
    downloaded_paths = []

    granule_ids = [
        pairs_df.loc[pair_index, "granule1"],
        pairs_df.loc[pair_index, "granule2"]
    ]

    for gran_id in granule_ids:
        match = gdf_results[gdf_results['fileID'] == gran_id]
        if match.empty:
            print(f"Granule {gran_id} not found in gdf_results. Skipping.")
            downloaded_paths.append(None)
            continue

        download_url = match.iloc[0]['url']
        filename = os.path.basename(download_url)
        filepath = output_dir / filename

        if filepath.exists() and not overwrite:
            print(f"Already exists: {filename}")
            downloaded_paths.append(filepath)
            continue

        # Download with HTTP Basic Auth
        print(f"Downloading {filename}...")
        with requests.get(download_url, auth=(username, password), stream=True) as response:
            if response.status_code == 200:
                total = int(response.headers.get("content-length", 0))
                with open(filepath, "wb") as f, tqdm(
                    desc=filename,
                    total=total,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024
                ) as bar:
                    for chunk in response.iter_content(chunk_size=1024):
                        size = f.write(chunk)
                        bar.update(size)
                print(f"Downloaded: {filename}")
                downloaded_paths.append(filepath)
            else:
                print(f"Failed to download {filename} (HTTP {response.status_code})")
                downloaded_paths.append(None)

    return tuple(downloaded_paths)


def unzip_file(zip_path):
    """
    Uncompress a zip file into the same directory where the zip resides.

    Parameters:
        zip_path (str or Path): Path to the zip file.

    Returns:
        list[Path]: List of full paths to the extracted files.
    """
    zip_path = Path(zip_path)
    extract_to = zip_path.parent  # same directory as the zip file

    extracted_files = []
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for file_name in zip_ref.namelist():
            extracted_path = zip_ref.extract(file_name, path=extract_to)
            extracted_files.append(Path(extracted_path))

    return extracted_files


def get_hh_tiff(paths: List[Path]) -> Optional[Path]:
    """
    From a list of Paths inside a Sentinel-1 SAFE structure,
    return the HH measurement TIFF (the one containing '-hh-' in the filename).

    Returns:
        Path or None if no HH TIFF is found.
    """
    for p in paths:
        name = p.name.lower()
        if name.endswith((".tif", ".tiff")) and "-hh-" in name:
            return p
    return None
