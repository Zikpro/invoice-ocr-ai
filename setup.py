from setuptools import setup, find_packages


setup(
    name="zikpro_invoice_ocr",
    version="0.0.2",
    description="AI-powered Invoice OCR to Purchase Invoice automation using DeepInfra",
    author="Zikpro Ltd",
    author_email="info@zikpro.com",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "frappe>=15.0.0",
    ],
)
