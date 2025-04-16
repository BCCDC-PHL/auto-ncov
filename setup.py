from setuptools import setup, find_namespace_packages


setup(
    name='auto-ncov',
    version='0.1.0',
    packages=find_namespace_packages(),
    entry_points={
        "console_scripts": [
            "auto-ncov = auto_ncov.__main__:main",
        ]
    },
    scripts=[],
    package_data={
    },
    install_requires=[
    ],
    description='Automated analysis of SARS-CoV-2 sequence data',
    url='https://github.com/BCCDC-PHL/auto-ncov',
    author='Dan Fornika',
    author_email='dan.fornika@bccdc.ca',
    include_package_data=True,
    keywords=[],
    zip_safe=False
)
