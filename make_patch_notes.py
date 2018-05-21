#!/usr/bin/env python3

import argparse
import json

DIFF_FIELDS = ['tier', 'column', 'plaintext_full_tooltip', 'plaintext_short_tooltip', 'icon', 'tree_name', 'face_name']

if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('old_version')
    args.add_argument('new_version')
    args = args.parse_args()

    with open(args.old_version) as f:
        old_version = json.load(f)
    with open(args.new_version) as f:
        new_version = json.load(f)

    if old_version['info']['build'] >= new_version['info']['build']:
        print('Warning: {} is not an older version than {}'.format(
            old_version['info']['build'], new_version['info']['build']))

    patch_notes_file = open('./out/patch_notes_{}_{}.txt'.format(
        old_version['info']['build'], new_version['info']['build']), 'w')
    print('# Patch notes: {} -> {}\n'.format(
        old_version['info']['build'], new_version['info']['build']), file=patch_notes_file)

    for hero in sorted(old_version['heroes']):
        printed_hero_name = False
        old_talents = {}
        new_talents = {}
        for talent in old_version['heroes'][hero]['talents']:
            old_talents[talent['english_name']] = talent
        for talent in new_version['heroes'][hero]['talents']:
            new_talents[talent['english_name']] = talent
        for name, talent in old_talents.items():
            if name not in new_talents:
                if not printed_hero_name:
                    print('\n## {}'.format(hero), file=patch_notes_file)
                    printed_hero_name = True
                print('\n### {}\n\nTalent removed (tier {}).\n{}\n'.format(
                    name, talent['tier'], talent['plaintext_full_tooltip']), file=patch_notes_file)
                continue
            new_talents[name]['checked'] = True
            printed_talent_name = False
            for field in DIFF_FIELDS:
                if talent[field] != new_talents[name][field]:
                    if not printed_hero_name:
                        print('\n## {}'.format(hero), file=patch_notes_file)
                        printed_hero_name = True
                    if not printed_talent_name:
                        print('\n### {}\n'.format(name), file=patch_notes_file)
                        printed_talent_name = True
                    print('Changed {}:\n{}\n->\n{}\n'.format(
                        field, talent[field], new_talents[name][field]), file=patch_notes_file)
        for name, talent in new_talents.items():
            if 'checked' not in talent:
                print('\n### {}\n\nNew talent (tier {}).\n{}\n'.format(
                    name, talent['tier'], talent['plaintext_full_tooltip']), file=patch_notes_file)
    patch_notes_file.close()
