# NISAR_SeaIce
Repository for L3 science products for the Sea Ice Motion workflow.

## Installation

### 1. Clone this repo

```bash
git clone https://github.com/JPLSeaIce/NISAR_SeaIce
cd NISAR_SeaIce
```

### 2. Create the conda environment

```bash
conda env create -f requirements.yml
conda activate sea-ice
```

This installs all dependencies including [RGPSPy](https://github.com/JPLSeaIce/RGPSPy).

### 3. Unzip motion grid files

```bash
unzip 'motion_grids/*.zip' -d motion_grids/
```

### 4. Configure Earthdata credentials

Add your [NASA Earthdata](https://urs.earthdata.nasa.gov) credentials to `~/.netrc`:

```
machine urs.earthdata.nasa.gov
    login <your_username>
    password <your_password>
```

### 5. Sea Ice Motion notebook

Open [`generate_sea_ice_motion.ipynb`](generate_sea_ice_motion.ipynb) to run the full sea ice motion workflow.
