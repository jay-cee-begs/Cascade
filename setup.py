from setuptools import setup, find_packages

setup(
    name="cascade2p",
    version="1.0",
    description="Calibrated inference of spiking from calcium ΔF/F data using deep networks",
    author="Peter Rupprecht",
    author_email="",
    packages=find_packages(),
    python_requires=">=3.7, <3.9", #updated to allow all python < 3.9
    install_requires=[ # original install_requirements
        "numpy",
        "scipy",
        "matplotlib",
        "tensorflow==2.3",  # pip install CPU and GPU tensorflow
        "keras==2.3.1",
        "h5py",
        "seaborn",
        "ruamel.yaml",
   """ install_requires=[ #to match suite2p-req.txt file
        
        "numpy==1.24.4",  # Matches suite2p38.txt to ensure npy compatibility
        "scipy==1.10.1",  # Updated to match suite2p38.txt for matrix operations
        "matplotlib==3.7.5",
        "tensorflow==2.4.1",  # Aligned with the latest supported stable version for Suite2p
        "keras==2.3.1",  # Keras version is fine but monitor for compatibility
        "h5py==3.10.0",  # Matches both environments for HDF5 file handling
        "seaborn==0.13.2",
        "ruamel.yaml==0.18.10",
        "spyder",
    ],
    install_requires=[ #for tensorflow 2.3
        "numpy>=1.19.5,<=1.24.4",  # TensorFlow 2.3 works fine with this range
        "scipy==1.10.1",  # Updated for compatibility with both TensorFlow and Suite2p
        "matplotlib==3.7.5",
        "tensorflow==2.3",
        "keras==2.3.1",  # Same version to match TensorFlow
        "h5py==3.10.0",
        "seaborn==0.13.2",
        "ruamel.yaml==0.18.10",
        "spyder==6.0.3",
        "pandas==1.4.4",  # Consistent with Suite2p environment """
    ],
)
