"""
参考 https://www.lodashjs.com/
"""

from __future__ import annotations

import copy
from typing import List, Tuple, Callable

__all__ = ['split', 'pick', 'key_by', 'omit']


class LodashError(Exception):
    pass


def split(content, sep=',', func=None):
    """ '1, 2, 3' => [1, 2, 3] """
    content = content.strip()
    if not content:
        return []
    items = content.split(sep)
    if func:
        return list(map(func, items))
    return items


def pick(obj, keys: List[str] or Tuple[str]):
    """
    obj = { 'a': 1, 'b': '2', 'c': 3 }
    pick(obj, ['a', 'c']);
    // => { 'a': 1, 'c': 3 }
    """
    if len(keys) == 0:
        return {}
    if isinstance(obj, dict): # dict
        return {key: obj[key] for key in keys}
    else:   # obj
        return {key: getattr(obj, key) for key in keys}


def omit(obj_dict: dict, keys: List[str] or Tuple[str], deep=True):
    """
    { 'a': 1, 'b': '2', 'c': 3, 'd': [1, 2, 3] }
    omit(obj, ('a', 'c'))
    => {'b': '2', 'd': [1, 2, 3]}
    """
    copy_func = copy.deepcopy if deep else copy.copy
    if len(keys) == 0:
        return copy_func(obj_dict)
    all_keys_set = set(obj_dict.keys())
    keys_set = set(keys)
    delta_keys_set = all_keys_set - keys_set
    return {key: copy_func(obj_dict[key]) for key in delta_keys_set}



def key_by(arr, key: str or Callable):
    """
    array = [{ 'dir': 'left', 'code': 97 }, { 'dir': 'right', 'code': 100 }]
    key_by(array, lambda o: chr(o['code']))
    // => { 'a': { 'dir': 'left', 'code': 97 }, 'd': { 'dir': 'right', 'code': 100 } }
    key_by(array, 'dir');
    // => { 'left': { 'dir': 'left', 'code': 97 }, 'right': { 'dir': 'right', 'code': 100 } }
    """
    if len(arr) == 0:
        return {}
    if callable(key):
        return {key(obj): obj for obj in arr}
    else:
        if isinstance(arr[0], dict):
            return {obj[key]: obj for obj in arr}
        else:
            return {getattr(obj, key): obj for obj in arr}




if __name__ == '__main__':
    print(pick({'a': 1, 'b': '2', 'c': 3}, ('a', 'c')))

    array = [{'dir': 'left', 'code': 97}, {'dir': 'right', 'code': 100}]
    obj = { 'a': 1, 'b': '2', 'c': 3, 'd': [1, 2, 3] }
    print(key_by(array, lambda o: chr(o['code'])))
    print(key_by(array, 'dir'))
    obj1 = omit(obj, ('a', 'c'))
    obj1['d'].append(4)
    print(obj1)
    print(obj)