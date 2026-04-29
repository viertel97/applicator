import io

import mammoth


def docx_bytes_to_markdown(data: bytes) -> str:
    result = mammoth.convert_to_markdown(io.BytesIO(data))
    return result.value.strip()
