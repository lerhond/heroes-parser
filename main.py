#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from collections import defaultdict
from html.parser import HTMLParser
from itertools import chain


CONSTS = {
    # Valla - Strafe, E.T.C. - Stage Dive, Muradin - Haymaker, Tyrande - Starfall
    'Effect,StormDamage,AttributeFactor[Heroic]': 0,
    # Greymane - Hunter's Blunderbuss
    'Behavior,GreymaneHuntersBlunderbussCarryBehavior,DamageResponse.ModifyFraction': 1,
    # Greymane - Tooth and Claw
    'Behavior,ToothAndClawCarryBehavior,DamageResponse.ModifyFraction': 1,
    # Yrel - Word of Glory
    'Effect,YrelArdentDefenderWordOfGloryCreateHealer,MultiplicativeModifierArray[WordOfGlory].Modifier': 0,
    # Azmodan - Azmodan - Sin's Grasp
    'Ability,AzmodanAllShallBurn,Cost[0].CooldownTimeUse': 1,

    #Auriel - Bestow Hope
    '$BehaviorTokenCount:AurielRayOfHeavenReservoirOfHopeQuestToken$' : 0,
    #Azmodan - Summon Demon Warrior
    'Behavior,AzmodanSummonDemonWarriorBurningDemonBuff,Period' : 1,
    #Kel'Thuzad - Master of the Cold Dark
    '$BehaviorStackCount:KelThuzadMasterOfTheColdDarkToken$' : 0,
    #Tyrael - El'druin's Might
    'Effect,ElDruinsMightDamage,AttributeFactor[Structure]' : 0,
    #Varian - Parry
    'Behavior,VarianParryIncomingDamageReduction,DamageResponse.ModifyFraction' : 0,
}

MATH_SYMBOLS = ['+', '-', '/', '*', '(', ')']

path_to_hots = None


def run_extractor(files):
    for file in files:
        print('Extracting', file)
        subprocess.run(
            ['./CASCExtractor/build/bin/CASCExtractor', path_to_hots, '-f', '-o', './extract/'] + [file],
            stdout=subprocess.DEVNULL)


def mkdir(path):
    try:
        os.mkdir(path)
    except FileExistsError:
        pass


def rmdir(path):
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass


def slug(text):
    ret = ''
    for c in text:
        if 'a' <= c <= 'z':
            ret += c
        elif 'A' <= c <= 'Z':
            if ret:
                ret += '-'
            ret += c.lower()
    return ret


def get_children(node, fun):
    if isinstance(node, list):
        ret = []
        for child in node:
            ret += list(get_children(child, fun))
        return ret
    elif isinstance(node, ET.Element):
        return list(filter(fun, node))
    else:
        raise TypeError('node should be either list or ET.Element, not ' + str(type(root)))


def num(s):
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def calculate_math(expr):
    while expr[-1] in ['+', '-', '*', '/']:
        expr = expr[:-1]
    while '(' in expr:
        last_open = None
        for i, c in enumerate(expr):
            if c == '(':
                last_open = i
            elif c == ')':
                expr = expr[:last_open] + str(calculate_math(expr[last_open+1:i])) + expr[i+1:]
                break
    n = ''
    op = None
    res = 0
    expr += 'X'
    for c in expr:
        if c in ['+', '-', '*', '/', 'X']:
            if n == '' and c == '-':
                n += '-'
                continue
            if n == '-' and c == '-':
                n = ''
                continue
            n = num(n)
            if op is None:
                res = n
            elif op == '+':
                res = res + n
            elif op == '-':
                res = res - n
            elif op == '*':
                res = res * n
            elif op == '/':
                res = res / n
            op = c
            n = ''
        else:
            n += c
    return res


def get_value_by_path(roots, path, skip_beginning=False):
    if path in CONSTS:
        return CONSTS[path]
    path = path.replace('.', ',')
    while path.endswith(','):
        path = path[:-1]
    path = path.split(',')
    if not skip_beginning:
        node = get_children(roots, lambda el: ('C' + path[0]) in el.tag and el.attrib.get('id') == path[1])
    else:
        node = roots
    if not node:
        return None
    for i, name in enumerate(path):
        if not skip_beginning and i < 2:
            continue
        if isinstance(node, str):
            break
        found = False
        if not found and name and name[-1] == ']':
            name, index = name[:-1].split('[')
            for i, child in enumerate(get_children(node, lambda el: el.tag == name)):
                if str(i) == index or child.attrib.get('index') == index:
                    node = child
                    found = True
                    break
        if not found and isinstance(node, ET.Element) and name in node.attrib:
            node = node.attrib[name]
            found = True
        if not found:
            res = get_children(node, lambda el: el.tag == name)
            if res:
                node = res[0]
                found = True
        if not found:
            if isinstance(node, list):
                if len(node) == 1:
                    node = node[0]
                else:
                    return None
            if 'parent' in node.attrib:
                v = get_value_by_path(roots, ','.join([path[0], node.attrib['parent']] + path[i:]))
                return v
            deft = get_children(roots, lambda el: el.tag == node.tag and el.attrib.get('default') == '1' and 'id' not in el.attrib)
            if deft:
                return get_value_by_path(deft, ','.join(path[i:]), skip_beginning=True)
            return None
    if isinstance(node, str):
        return num(node)
    if 'value' in node.attrib:
        return num(node.attrib['value'])
    if 'Value' in node.attrib:
        return num(node.attrib['Value'])
    return None


def split_on_math(ref):
    if ref in CONSTS:
        return [str(CONSTS[ref])]
    ret = ['']
    for c in ref:
        if c.isspace():
            continue
        if c in MATH_SYMBOLS:
            if ret[-1] == '':
                ret = ret[:-1]
            ret += [c]
            ret += ['']
        else:
            ret[-1] += c
    if ret[0] == '':
        ret = ret[1:]
    if ret[-1] == '':
        ret = ret[:-1]
    return ret


replace_ref_regex = re.compile(r"\[d.+?ref='(.+?)'.+?\]")
precision_regex = re.compile(r"precision='(\d+)'")

roots = []


def repl_function(ref):
    if any(math_sym in ref.group(1) for math_sym in MATH_SYMBOLS):
        return '(' + ref.group(1) + ')'

    res = get_value_by_path(roots, ref.group(1))

    precision = precision_regex.search(ref.group(0))
    if precision is None:
        precision = 0
    else:
        precision = int(precision.group(1))

    if isinstance(res, float):
        res = round(res, precision)
    if isinstance(res, float) and res.is_integer():
        res = round(res)

    return str(res)


class TooltipParser(HTMLParser):
    plaintext_tooltip = ''
    html_tooltip = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ['c','s']:
            self.html_tooltip += '<span class="{}">'.format(slug(attrs['val']))
        else:
            print('WARNING - unknown start tag:', tag, attrs, file=sys.stderr)

    def handle_endtag(self, tag):
        if tag in ['c','s']:
            self.html_tooltip += '</span>'
        elif tag == 'n':
            self.plaintext_tooltip += '\n'
            self.html_tooltip += '<br />'
        else:
            print('WARNING - unknown end tag:', tag, file=sys.stderr)

    def handle_startendtag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'd':
            for key in attrs:
                if key not in ['ref', 'precision', 'score'] and not (key == 'player' and attrs[key] == '0'):
                    print('WARNING - unknown attribute of <d />:', key, attrs[key], file=sys.stderr)
            if 'ref' in attrs:
                ref = attrs['ref']
                ref = replace_ref_regex.sub(repl_function, ref)
                ref = split_on_math(ref)
                math_exp = ''
            else:
                ref = []
                if 'score' in attrs and attrs['score'] == 'LostVikingsVikingBriberyStackScore':
                    math_exp = '0'
                elif 'score' in attrs and attrs['score'] == 'GenericHeroRealScoreValue1':
                    math_exp = '0'
                else:
                    math_exp = 'None'
                    print('WARNING - no ref or score in attrs of <d />', tag, attrs)
            for path in ref:
                if path not in MATH_SYMBOLS:
                    x = num(path)
                    if x is None:
                        x = get_value_by_path(roots, path)
                    math_exp += '(' + str(x) + ')'
                else:
                    math_exp += path
            if 'None' in math_exp:
                res = None
                print('WARNING - expression evaluated to none:', attrs['ref'], math_exp, '---', file=sys.stderr)
            else:
                open_count = math_exp.count('(')
                closed_count = math_exp.count(')')
                if open_count < closed_count:
                    math_exp = '(' * (closed_count - open_count) + math_exp
                elif open_count > closed_count:
                    math_exp += ')' * (open_count - closed_count)
                res = calculate_math(math_exp)
                if isinstance(res, float):
                    res = round(res, int(attrs.get('precision', 0)))
                if isinstance(res, float) and res.is_integer():
                    res = round(res)
            self.plaintext_tooltip += str(res)
            self.html_tooltip += str(res)
        elif tag == 'n':
            self.plaintext_tooltip += '\n'
            self.html_tooltip += '<br />'
        elif tag == 'img':
            self.html_tooltip += '<img src="{}" />'.format(slug(attrs['path']))
        else:
            print('WARNING - unknown startend tag:', tag, attrs, file=sys.stderr)

    def handle_data(self, data):
        self.plaintext_tooltip += data
        self.html_tooltip += data

    def feed(self, data):
        super().feed(data)


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) != 1:
        print('You need to provide a path to a Heroes of the Storm installation, or --skip-extracting.\n'
              'When using --skip-extracting, provide extracted files in ./extract/.')
        sys.exit(1)
    if '--skip-extracting' != args[0] and not os.path.isdir(args[0]):
        print('{} is not a directory.'.format(args[0]))
        sys.exit(1)
    skip_extracting = '--skip-extracting' == args[0]
    if not skip_extracting:
        path_to_hots = args[0]

    if not skip_extracting:
        rmdir('./extract/')
        os.mkdir('./extract/')
        run_extractor([
            'mods/core.stormmod/base.stormdata/BuildId.txt',
            'mods/core.stormmod/base.stormdata/GameData/*.xml',
            'mods/heroesdata.stormmod/base.stormdata/*.xml',
            'mods/heroesdata.stormmod/enus.stormdata/*',
            'mods/heromods/*.xml',
            'mods/heromods/*.txt'
        ])

    with open('./extract/mods/core.stormmod/base.stormdata/BuildId.txt') as f:
        build_id = f.read()
    build_id = int(build_id.replace('B', ''))
    print('Game build:', build_id)

    trees = []
    game_strings = {}

    print('Reading files')
    for root, dirs, files in chain(
            os.walk('./extract/mods/heromods/'),
            os.walk('./extract/mods/heroesdata.stormmod/base.stormdata/GameData/'),
            os.walk('./extract/mods/heroesdata.stormmod/enus.stormdata'),
            os.walk('./extract/mods/core.stormmod/base.stormdata/GameData')):
        for file in files:
            full_path = os.path.join(root, file)
            if full_path.endswith('.xml') and 'SkinData' not in full_path and 'SoundData' not in full_path:
                tree = ET.parse(full_path)
                trees.append(tree)
                roots.append(tree.getroot())
            elif full_path.endswith('GameStrings.txt') and 'enus' in full_path:
                with open(full_path, 'r', encoding='utf-8') as f:
                    tmp = f.read().strip().split('\n')
                for line in tmp:
                    line = line.strip().split('=')
                    key = line[0]
                    val = '='.join(line[1:])
                    game_strings[key] = val

    print('Parsing hero data')
    talent_faces = {}
    for child in get_children(roots, lambda el: el.tag == 'CTalent'):
        c = get_children(child, lambda el: el.tag == 'Face')
        if c:
            talent_faces[child.attrib['id']] = c[0].attrib['value']

    icons = {}
    tooltips = {}
    simple_tooltips = {}
    for child in get_children(roots, lambda el: el.tag == 'CButton' and 'id' in el.attrib):
        c = get_children(child, lambda el: el.tag == 'Icon')
        if c:
            icons[child.attrib['id']] = c[0].attrib['value']
        t = get_children(child, lambda el: el.tag == 'Tooltip')
        if t:
            tooltips[child.attrib['id']] = t[0].attrib['value']
        st = get_children(child, lambda el: el.tag == 'SimpleDisplayText')
        if st:
            simple_tooltips[child.attrib['id']] = st[0].attrib['value']

    heroes = {}
    hero_nodes = get_children(roots, lambda el: el.tag == 'CHero')
    icon_set = set()

    for hero in sorted(hero_nodes, key=lambda h: str(h.attrib.get('id'))):
        talent_nodes = get_children(hero, lambda el: el.tag == 'TalentTreeArray')
        if not talent_nodes:
            continue
        print(hero.attrib['id'])
        talents = []
        for talent in talent_nodes:
            face_name = talent_faces[talent.attrib['Talent']]
            icon = icons[face_name]
            if icon.startswith('Assets\\Textures\\'):
                icon = icon[len('Assets\\Textures\\'):].lower()
                icon_set.add(icon)
            else:
                print('WARNING - unexpected icon path:', icon)
            talent = {
                'tree_name': talent.attrib['Talent'],
                'face_name': face_name,
                'tier': int(talent.attrib['Tier']),
                'column': int(talent.attrib['Column']),
                'english_name': game_strings['Button/Name/' + face_name],
                'unparsed_short_tooltip': game_strings[simple_tooltips.get(face_name) or ('Button/SimpleDisplayText/' + face_name)],
                'unparsed_full_tooltip': game_strings[tooltips.get(face_name) or ('Button/Tooltip/' + face_name)],
                'icon': icon
            }
            talents.append(talent)
        talents = sorted(talents, key=lambda t: (t['tier'], t['column']))
        for talent in talents:
            parser = TooltipParser()
            parser.feed(talent['unparsed_short_tooltip'])
            del talent['unparsed_short_tooltip']
            talent['plaintext_short_tooltip'] = parser.plaintext_tooltip.strip()
            talent['html_short_tooltip'] = parser.html_tooltip.strip()
            parser = TooltipParser()
            parser.feed(talent['unparsed_full_tooltip'])
            del talent['unparsed_full_tooltip']
            talent['plaintext_full_tooltip'] = parser.plaintext_tooltip.strip()
            talent['html_full_tooltip'] = parser.html_tooltip.strip()

        ability_nodes = get_children(hero, lambda el: el.tag == 'HeroAbilArray')
        abilities = []
        for ability in ability_nodes:
            base_ability = get_children(ability, lambda el: el.tag == 'Flags' and el.attrib.get('index') == 'ShowInHeroSelect' and el.attrib.get('value') == '1')
            if not base_ability:
                continue
            face_name = ability.attrib.get('Button') or ability.attrib.get('Abil')
            icon = icons[face_name]
            if icon.startswith('Assets\\Textures\\'):
                icon = icon[len('Assets\\Textures\\'):].lower()
                icon_set.add(icon)
            else:
                print('WARNING - unexpected icon path:', icon)
            abil = {
                'face_name': face_name,
                'english_name' : game_strings['Button/Name/' + face_name],
                'unparsed_short_tooltip': game_strings.get(simple_tooltips.get(face_name)) or game_strings.get('Button/SimpleDisplayText/' + face_name, ''),
                'unparsed_full_tooltip': game_strings.get(tooltips.get(face_name)) or game_strings.get('Button/Tooltip/' + face_name, ''),
                'icon': icon
            }
            abilities.append(abil)
        for ability in abilities:
            parser = TooltipParser()
            parser.feed(ability['unparsed_short_tooltip'])
            del ability['unparsed_short_tooltip']
            ability['plaintext_short_tooltip'] = parser.plaintext_tooltip.strip()
            ability['html_short_tooltip'] = parser.html_tooltip.strip()
            parser = TooltipParser()
            parser.feed(ability['unparsed_full_tooltip'])
            del ability['unparsed_full_tooltip']
            ability['plaintext_full_tooltip'] = parser.plaintext_tooltip.strip()
            ability['html_full_tooltip'] = parser.html_tooltip.strip()

        heroes[hero.attrib['id']] = {}
        heroes[hero.attrib['id']]['talents'] = talents
        heroes[hero.attrib['id']]['abilities'] = abilities

    print('Saving JSON')
    data = {
        'info': {
            'build': build_id,
        },
        'heroes': heroes,
    }
    mkdir('./out/')
    rmdir('./out/icons/')
    mkdir('./out/icons/')

    with open('out/heroes_{}.json'.format(build_id), 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True)

    if not skip_extracting:
        print('Extracting icons')
        run_extractor(['mods/heroes.stormmod/base.stormassets/Assets/Textures/storm_ui_icon_*.dds'])
    for icon in sorted(icon_set):
        icon_path = 'mods/heroes.stormmod/base.stormassets/Assets/Textures/' + icon
        if not (icon.startswith('storm_ui_icon_') and icon.endswith('.dds')):
            run_extractor([icon_path])
        shutil.copy('./extract/' + icon_path, './out/icons/')

    print('Converting icons to PNG')
    subprocess.run(['mogrify',
                    '-format', 'png',
                    '-define', 'png:compression-filter=2',
                    '-define', 'png:compression-level=9',
                    '-define', 'png:compression-strategy=0',
                    './*'], cwd='./out/icons/')
    for file in os.listdir('./out/icons'):
        if not file.endswith('.png'):
            os.remove('./out/icons/' + file)
