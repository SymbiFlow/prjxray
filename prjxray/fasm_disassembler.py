import re
import fasm
from prjxray import bitstream


def mk_fasm(tile_name, feature):
    """ Convert matches tile and feature to FasmLine tuple. """
    # Seperate addressing of multi-bit features:
    # TILE.ALUT[0] -> ('TILE', 'ALUT', '0')
    # TILE.ALUT.SMALL -> ('TILE', 'ALUT.SMALL', None)
    m = re.match(r'([A-Za-z0-9_]+).([^\[]+)(\[[0-9]+\])?', feature)
    tag_post = m.group(2)
    address = None
    if m.group(3) is not None:
        address = int(m.group(3)[1:-1])

    feature = '{}.{}'.format(tile_name, tag_post)

    return fasm.FasmLine(
        set_feature=fasm.SetFasmFeature(
            feature=feature,
            start=address,
            end=None,
            value=1,
            value_format=None,
        ),
        annotations=None,
        comment=None)


class FasmDisassembler(object):
    """ Given a Project X-ray data, outputs FasmLine tuples for bits set. """

    def __init__(self, db):
        self.db = db
        self.grid = self.db.grid()
        self.segment_map = self.grid.get_segment_map()
        self.decode_warnings = set()

    def find_features_in_tile(self, tile_name, bits, bitdata, verbose=False):
        gridinfo = self.grid.gridinfo_at_tilename(tile_name)

        try:
            tile_segbits = self.db.get_tile_segbits(gridinfo.tile_type)
        except KeyError as e:
            if not verbose:
                return

            if gridinfo.tile_type in self.decode_warnings:
                return

            comment = " WARNING: failed to load DB for tile type {}".format(
                gridinfo.tile_type)
            yield fasm.FasmLine(
                set_feature=None,
                annotations=None,
                comment=comment,
            )
            yield fasm.FasmLine(
                set_feature=None,
                annotations=[
                    fasm.Annotation('missing_segbits', gridinfo.tile_type),
                    fasm.Annotation('exception', str(e)),
                ],
                comment=None,
            )

            self.decode_warnings.add(gridinfo.tile_type)
            return

        for ones_matched, feature in tile_segbits.match_bitdata(bits, bitdata):
            for frame, bit in ones_matched:
                bitdata[frame][1].remove(bit)

            yield mk_fasm(tile_name=tile_name, feature=feature)

    def find_features_in_bitstream(self, bitdata, verbose=False):
        frames = set(bitdata.keys())
        tiles_checked = set()

        while len(frames) > 0:
            frame = frames.pop()

            # Skip frames that were emptied in a previous iteration.
            if not bitdata[frame]:
                continue

            # Iterate over all tiles that use this frame.
            for bits_info in self.segment_map.segment_info_for_frame(frame):
                # Don't examine a tile twice
                if bits_info.tile in tiles_checked:
                    continue

                # Check if this frame has any data for the relevant tile.
                any_column = False
                for word_idx in range(bits_info.bits.words):
                    if word_idx + bits_info.bits.offset in bitdata[frame][0]:
                        any_column = True
                        break

                if not any_column:
                    continue

                tiles_checked.add(bits_info.tile)

                for fasm_line in self.find_features_in_tile(
                        bits_info.tile, bits_info.bits, bitdata,
                        verbose=verbose):
                    yield fasm_line

            if len(bitdata[frame][1]) > 0 and verbose:
                # Some bits were not decoded, add warning and annotations to
                # FASM.
                yield fasm.FasmLine(
                    set_feature=None,
                    annotations=None,
                    comment=" In frame 0x{:08x} {} bits were not converted.".
                    format(
                        frame,
                        len(bitdata[frame][1]),
                    ))

                for bit in bitdata[frame][1]:
                    wordidx = bit // bitstream.WORD_SIZE_BITS
                    bitidx = bit % bitstream.WORD_SIZE_BITS
                    annotation = fasm.Annotation(
                        'unknown_bit', '{:08x}_{}_{}'.format(
                            frame, wordidx, bitidx))
                    yield fasm.FasmLine(
                        set_feature=None,
                        annotations=[annotation],
                        comment=None,
                    )