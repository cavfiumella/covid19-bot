
version_info = (0,5,0)

def get_version() -> str:
    version = ".".join(str(x) for x in version_info)
    return version
