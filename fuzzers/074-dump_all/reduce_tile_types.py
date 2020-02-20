""" Reduce tile types to prototypes that are always correct.

The dump-all generate.tcl dumps all instances of each tile type.  Some tiles
are missing wires.  reduce_tile_types.py generates the superset tile that
encompases all tiles of that type.  If it is not possible to generate a super
set tile, an error will be generated.

"""

import argparse
import prjxray.lib
import prjxray.node_lookup
import datetime
import os.path
import pyjson5 as json5
import progressbar
import multiprocessing
import os
import functools
import json
from prjxray.xjson import extract_numbers


def check_and_strip_prefix(name, prefix):
    assert name.startswith(prefix), repr((name, prefix))
    return name[len(prefix):]


def flatten_site_pins(tile, site, site_pins, site_pin_node_to_wires):
    def inner():
        for site_pin in site_pins:
            wires = tuple(site_pin_node_to_wires(tile, site_pin['node']))

            if len(wires) == 0:
                yield (
                    check_and_strip_prefix(site_pin['site_pin'], site + '/'),
                    None)
                continue

            assert len(wires) == 1, repr(wires)

            pin_info = {
                'wire': wires[0],
                'delay': site_pin['delay'],
            }

            if 'cap' in site_pin:
                pin_info['cap'] = site_pin['cap']

            if 'res' in site_pin:
                pin_info['res'] = site_pin['res']

            yield (
                check_and_strip_prefix(site_pin['site_pin'], site + '/'),
                pin_info)

    return dict(inner())


def compare_sites_and_update(tile, sites, new_sites):
    for site_a, site_b in zip(sites, new_sites):
        assert site_a['type'] == site_b['type']
        assert site_a['site_pins'].keys() == site_b['site_pins'].keys()

        for site_pin in site_a['site_pins']:
            if site_a['site_pins'][site_pin] is not None and site_b[
                    'site_pins'][site_pin] is not None:
                assert site_a['site_pins'][site_pin] == site_b['site_pins'][
                    site_pin]
            elif site_a['site_pins'][site_pin] is None and site_b['site_pins'][
                    site_pin] is not None:
                site_a['site_pins'][site_pin] = site_b['site_pins'][site_pin]


def get_prototype_site(site):
    proto = {}
    proto['type'] = site['type']
    proto['site_pins'] = {}
    proto['site_pips'] = {}
    for site_pin in site['site_pins']:
        name = check_and_strip_prefix(site_pin['site_pin'], site['site'] + '/')

        proto['site_pins'][name] = {
            'direction': site_pin['direction'],
        }

    for site_pip in site['site_pips']:
        name = check_and_strip_prefix(site_pip['site_pip'], site['site'] + '/')

        proto['site_pips'][name] = {
            'to_pin': site_pip['to_pin'],
            'from_pin': site_pip['from_pin'],
        }

    return proto


def get_pips(tile, pips):
    proto_pips = {}

    for pip in pips:
        name = check_and_strip_prefix(pip['pip'], tile + '/')

        proto_pips[name] = {
            'src_wire':
            check_and_strip_prefix(pip['src_wire'], tile + '/')
            if pip['src_wire'] is not None else None,
            'dst_wire':
            check_and_strip_prefix(pip['dst_wire'], tile + '/')
            if pip['dst_wire'] is not None else None,
            'is_pseudo':
            pip['is_pseudo'],
            'is_directional':
            pip['is_directional'],
            'can_invert':
            pip['can_invert'],
            'is_pass_transistor':
            pip['is_pass_transistor'],
            'src_to_dst': {
                'delay': pip.get('forward_delay', None),
                'in_cap': pip.get('forward_in_cap', None),
                'res': pip.get('forward_res', None),
            },
            'dst_to_src': {
                'delay': pip.get('reverse_delay', None),
                'in_cap': pip.get('reverse_in_cap', None),
                'res': pip.get('reverse_res', None),
            },
        }

    return proto_pips


def compare_and_update_pips(pips, new_pips):
    # Pip names are always the same, but sometimes the src_wire or dst_wire
    # may be missing.

    assert pips.keys() == new_pips.keys(), repr((pips.keys(), new_pips.keys()))
    for name in pips:
        if pips[name]['src_wire'] is not None and new_pips[name][
                'src_wire'] is not None:
            assert pips[name]['src_wire'] == new_pips[name]['src_wire'], repr(
                (
                    pips[name]['src_wire'],
                    new_pips[name]['src_wire'],
                ))
        elif pips[name]['src_wire'] is None and new_pips[name][
                'src_wire'] is not None:
            pips[name]['src_wire'] = new_pips[name]['src_wire']

        if pips[name]['dst_wire'] is not None and new_pips[name][
                'dst_wire'] is not None:
            assert pips[name]['dst_wire'] == new_pips[name]['dst_wire'], repr(
                (
                    pips[name]['dst_wire'],
                    new_pips[name]['dst_wire'],
                ))
        elif pips[name]['dst_wire'] is None and new_pips[name][
                'dst_wire'] is not None:
            pips[name]['dst_wire'] = new_pips[name]['dst_wire']

        for k in ['is_pseudo', 'is_directional', 'can_invert']:
            assert pips[name][k] == new_pips[name][k], (
                k, pips[name][k], new_pips[name][k])


def check_wires(wires, sites, pips):
    """ Verify that the wires generates from nodes are a superset of wires in
      sites and pips """
    if sites is not None:
        for site in sites:
            for wire_to_site_pin in site['site_pins'].values():
                if wire_to_site_pin is not None:
                    assert wire_to_site_pin['wire'] in wires, repr(
                        (wire_to_site_pin, wires))

    if pips is not None:
        for pip in pips.values():
            if pip['src_wire'] is not None:
                assert pip['src_wire'] in wires, repr((pip['src_wire'], wires))
            if pip['dst_wire'] is not None:
                assert pip['dst_wire'] in wires, repr((pip['dst_wire'], wires))


def get_sites(tile, site_pin_node_to_wires):
    for site in tile['sites']:
        min_x_coord, min_y_coord = prjxray.lib.find_origin_coordinate(
            site['site'], (site['site'] for site in tile['sites']))

        orig_site_name = site['site']
        coordinate = prjxray.lib.get_site_coordinate_from_name(orig_site_name)

        x_coord = coordinate.x_coord - min_x_coord
        y_coord = coordinate.y_coord - min_y_coord

        yield (
            {
                'name':
                'X{}Y{}'.format(x_coord, y_coord),
                'prefix':
                coordinate.prefix,
                'x_coord':
                x_coord,
                'y_coord':
                y_coord,
                'type':
                site['type'],
                'site_pins':
                dict(
                    flatten_site_pins(
                        tile['tile'], site['site'], site['site_pins'],
                        site_pin_node_to_wires)),
            })


def read_json5(fname, database_file):
    node_lookup = prjxray.node_lookup.NodeLookup(database_file)

    with open(fname) as f:
        tile = json5.load(f)

    def get_site_types():
        for site in tile['sites']:
            yield get_prototype_site(site)

    site_types = tuple(get_site_types())
    sites = tuple(get_sites(tile, node_lookup.site_pin_node_to_wires))
    pips = get_pips(tile['tile'], tile['pips'])

    def inner():
        for wire in tile['wires']:
            assert wire['wire'].startswith(tile['tile'] + '/')

            if wire['res'] != '0.000' or wire['cap'] != '0.000':
                wire_delay_model = {
                    'res': wire['res'],
                    'cap': wire['cap'],
                }
            else:
                wire_delay_model = None

            yield wire['wire'][len(tile['tile']) + 1:], wire_delay_model

    wires = {k: v for (k, v) in inner()}
    wires_from_nodes = set(node_lookup.wires_for_tile(tile['tile']))
    assert len(wires_from_nodes - wires.keys()) == 0, repr(
        (wires, wires_from_nodes))

    return fname, tile, site_types, sites, pips, wires


def compare_and_update_wires(wires, new_wires):
    for wire in new_wires:
        if wire not in wires:
            wires[wire] = new_wires
        else:
            assert wires[wire] == new_wires[wire]


def reduce_tile(pool, site_types, tile_type, tile_instances, database_file):
    sites = None
    pips = None
    wires = None

    with progressbar.ProgressBar(max_value=len(tile_instances)) as bar:
        chunksize = 1
        if len(tile_instances) < chunksize * 2:
            iter = map(
                lambda file: read_json5(file, database_file), tile_instances)
        else:
            print(
                '{} Using pool.imap_unordered'.format(datetime.datetime.now()))
            iter = pool.imap_unordered(
                functools.partial(read_json5, database_file=database_file),
                tile_instances,
                chunksize=chunksize,
            )

        for idx, (fname, tile, new_site_types, new_sites, new_pips,
                  new_wires) in enumerate(iter):
            bar.update(idx)

            assert tile['type'] == tile_type, repr((tile['tile'], tile_type))

            for site_type in new_site_types:
                if site_type['type'] in site_types:
                    prjxray.lib.compare_prototype_site(
                        site_type, site_types[site_type['type']])
                else:
                    site_types[site_type['type']] = site_type

            # Sites are expect to always be the same
            if sites is None:
                sites = new_sites
            else:
                compare_sites_and_update(tile['tile'], sites, new_sites)

            if pips is None:
                pips = new_pips
            else:
                compare_and_update_pips(pips, new_pips)

            if wires is None:
                wires = new_wires
            else:
                compare_and_update_wires(wires, new_wires)

            bar.update(idx + 1)

    check_wires(wires, sites, pips)

    return {
        'tile_type': tile_type,
        'sites': sites,
        'pips': pips,
        'wires': wires,
    }


def main():
    parser = argparse.ArgumentParser(
        description=
        "Reduces raw database dump into prototype tiles, grid, and connections."
    )
    parser.add_argument('--root_dir', required=True)
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--ignore_cache', action='store_true')

    args = parser.parse_args()

    print('{} Reading root.csv'.format(datetime.datetime.now()))
    tiles, nodes = prjxray.lib.read_root_csv(args.root_dir)

    print('{} Loading node<->wire mapping'.format(datetime.datetime.now()))
    database_file = os.path.join(args.output_dir, 'nodes.db')
    if os.path.exists(database_file) and not args.ignore_cache:
        node_lookup = prjxray.node_lookup.NodeLookup(database_file)
    else:
        node_lookup = prjxray.node_lookup.NodeLookup(database_file)
        node_lookup.build_database(nodes=nodes, tiles=tiles)

    site_types = {}

    processes = multiprocessing.cpu_count()
    print('Running {} processes'.format(processes))
    pool = multiprocessing.Pool(processes=processes)

    for tile_type in sorted(tiles.keys()):
        #for tile_type in ['CLBLL_L', 'CLBLL_R', 'CLBLM_L', 'CLBLM_R', 'INT_L', 'INT_L']:
        tile_type_file = os.path.join(
            args.output_dir, 'tile_type_{}.json'.format(tile_type))
        site_types = {}
        if os.path.exists(tile_type_file):
            print(
                '{} Skip reduced tile for {}'.format(
                    datetime.datetime.now(), tile_type))
            continue
        print(
            '{} Generating reduced tile for {}'.format(
                datetime.datetime.now(), tile_type))
        reduced_tile = reduce_tile(
            pool, site_types, tile_type, tiles[tile_type], database_file)
        for site_type in site_types:
            with open(os.path.join(
                    args.output_dir, 'tile_type_{}_site_type_{}.json'.format(
                        tile_type, site_types[site_type]['type'])), 'w') as f:
                json.dump(site_types[site_type], f, indent=2, sort_keys=True)

        reduced_tile['sites'] = sorted(
            reduced_tile['sites'],
            key=lambda site: extract_numbers(
                '{}_{}'.format(site['name'], site['prefix'])))

        with open(tile_type_file, 'w') as f:
            json.dump(reduced_tile, f, indent=2, sort_keys=True)


if __name__ == '__main__':
    main()
