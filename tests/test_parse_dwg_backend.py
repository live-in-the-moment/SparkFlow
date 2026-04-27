from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.cad.entities import ParsedCad
from backend.cad.parse import CadParseOptions, parse_cad


class ParseDwgBackendTests(unittest.TestCase):
    def test_dwg_conversion_reuses_requested_dxf_backend(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dwg = root / 'sample.dwg'
            dxf = root / 'sample.dxf'
            dwg.write_bytes(b'dwg')
            dxf.write_text('0\nEOF\n', encoding='utf-8')

            with patch('backend.cad.parse.convert_dwg_to_dxf', return_value=dxf) as convert_mock:
                with patch('backend.cad.dxf_ezdxf.parse_ezdxf_dxf', return_value=ParsedCad('dxf_ezdxf_v1', (), {})) as ez_mock:
                    parsed = parse_cad(
                        dwg,
                        options=CadParseOptions(
                            dwg_backend='cli',
                            dwg_converter_cmd=['dummy'],
                            dxf_backend='ezdxf',
                        ),
                    )

            convert_mock.assert_called_once()
            ez_mock.assert_called_once_with(dxf)
            self.assertEqual(parsed.parser_id, 'dxf_ezdxf_v1')
            self.assertEqual(parsed.meta['chosen_dxf_backend'], 'ezdxf')
            self.assertEqual(parsed.meta['source_format'], 'dwg')
            self.assertEqual(parsed.meta['dwg_backend'], 'cli')


if __name__ == '__main__':
    unittest.main()
