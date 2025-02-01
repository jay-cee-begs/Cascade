from setuptools import setup, find_packages

setup(
    name="cascade2p",
    version="1.0",
    description="Calibrated inference of spiking from calcium ΔF/F data using deep networks",
    author="Peter Rupprecht",
    author_email="",
    packages=find_packages(),
    python_requires=">=3.7, <3.9",
    install_requires=[
        "numpy==1.21.6",
        "scipy",
        "matplotlib",
        "tensorflow==2.11.0",  # pip install CPU and GPU tensorflow
        "keras==2.11.0",
        "h5py",
        "seaborn",
        "ruamel.yaml",
        "spyder",
    ],
)
