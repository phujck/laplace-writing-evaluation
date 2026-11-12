"""Human document titles and filesystem-safe publication names."""
import re


def basename(title: str) -> str:
    return re.sub(r'[^\w-]+','-',str(title),flags=re.UNICODE).strip('-_')[:120] or 'Document'
