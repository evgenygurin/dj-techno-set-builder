# Apply TypeForm compatibility patch early, before any import that
# might trigger beartype → typing_extensions → TypeForm chain.
from app._compat import apply_python313_compatibility

apply_python313_compatibility()
