import os
from setuptools import setup, find_packages

setup(
    name='xitorch',
    version="0.1",
    description='Differentiable scientific computing library',
    url='https://github.com/xitorch/xitorch',
    author='xitorch-developer',
    author_email='',
    license='MIT',
    packages=find_packages(),
    python_requires=">=3.6",
    install_requires=[
        "numpy>=1.8.2",
        "scipy>=1.1.0",
        "matplotlib>=1.5.3",
        "torch>=1.5",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Physics",
        "Topic :: Scientific/Engineering :: Mathematics",
        "License :: OSI Approved :: MIT License",

        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    keywords="project library linear-algebra autograd",
    zip_safe=False
)
