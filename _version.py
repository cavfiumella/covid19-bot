
version_info = (0,6,1)

def get_version() -> str:
    version = ".".join(str(x) for x in version_info)
    return version
