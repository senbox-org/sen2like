"""Version of the Application."""

__version__ = '4.2.1'

_splitted_version = __version__.split('.')

_major = f"{int(_splitted_version[0]):02d}"
_minor = f"{int(_splitted_version[1]):02d}"

# sample :
# version = 4.1.0 => 04.01 | 0401
# version = 4.12.0 => 04.12  | 0412
baseline_dotted = f"{_major}.{_minor}"
baseline = f"{_major}{_minor}"
