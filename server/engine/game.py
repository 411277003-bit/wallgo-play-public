"""房間裡的對局：建立初始狀態、逾時代打、結束判定、倒數計時。"""
import random
import uuid

import gevent

from server.extensions import socketio
from server.state import rooms
from server.engine.rules import (allColors, boardSize, get_piece_index, get_valid_moves, get_valid_walls,
                                 next_shape, breakable_walls, evaluate_board, check_game_over)


def init_game_state(room_code, player_count, rules=1):
    activeColors = allColors[:player_count]
    placementQueue = activeColors + activeColors[::-1]
    
    playersInfo = {}
    playerTimes = {}
    for c in activeColors:
        playersInfo[c] = {"hasBreaker": True}
        playerTimes[c] = 90
        
    state = {
        'rules': 2 if rules == 2 else 1,   # 1 = 原版；2 = 每人一圓一方、破牆限棋子旁
        'moveDir': None,
        'gameId': uuid.uuid4().hex,   # 這一局的編號，全房共用；存戰績時用來去重
        'phase': 'placement',
        'turnIndex': 0,
        'activeColors': activeColors,
        'placementQueue': placementQueue,
        'movementOrder': activeColors.copy(),
        'pieces': [],
        'walls': [], # list of {"r":r, "c":c, "color":color}
        'territories': [],
        'playersInfo': playersInfo,
        'playerTimes': playerTimes,
        'selectedPieceIndex': -1,
        'movedPieceIndex': -1,
        'stepsTaken': 0,
        'timer_job': None # 用於儲存倒數計時協程
    }
    return state


def force_ai_move(room_code):
    """後端強制代打邏輯"""
    if room_code not in rooms or 'game_state' not in rooms[room_code]: return
    state = rooms[room_code]['game_state']
    
    if state['phase'] == 'game_over': return
    
    color = state['placementQueue'][state['turnIndex']] if state['phase'] == 'placement' else state['movementOrder'][state['turnIndex']]
    
    # 執行 AI 邏輯
    if state['phase'] == 'placement':
        empty_cells = []
        for r in range(0, boardSize, 2):
            for c in range(0, boardSize, 2):
                if get_piece_index(state['pieces'], r, c) == -1:
                    empty_cells.append({'r': r, 'c': c})
        if empty_cells:
            choice = random.choice(empty_cells)
            piece = {'color': color, 'r': choice['r'], 'c': choice['c']}
            shape = next_shape(state, color)
            if shape:
                piece['shape'] = shape
            state['pieces'].append(piece)
        
        state['turnIndex'] += 1
        if state['turnIndex'] >= len(state['placementQueue']):
            state['phase'] = 'movement'
            state['turnIndex'] = 0
            
    elif state['phase'] == 'wall_building':
        p = state['pieces'][state['movedPieceIndex']]
        possible_walls = get_valid_walls(state['walls'], p['r'], p['c'])
        if possible_walls:
            w = random.choice(possible_walls)
            state['walls'].append({'r': w['r'], 'c': w['c'], 'color': color})
            
        state['movedPieceIndex'] = -1
        state['selectedPieceIndex'] = -1
        state['stepsTaken'] = 0
        state['phase'] = 'movement'
        state['turnIndex'] = (state['turnIndex'] + 1) % len(state['movementOrder'])
        
    else: # movement / breaking
        my_pieces = [{'idx': i, **p} for i, p in enumerate(state['pieces']) if p['color'] == color]
        total_mobility = sum(len(get_valid_moves(state['pieces'], state['walls'], p['r'], p['c'])) for p in my_pieces)
        
        my_walls = breakable_walls(state, color)
        if state['playersInfo'][color]['hasBreaker'] and my_walls and (total_mobility <= 2 or state['phase'] == 'wall_breaking'):
            w_to_break = random.choice(my_walls)
            state['walls'].remove(w_to_break)
            state['playersInfo'][color]['hasBreaker'] = False

        best_action = None
        best_score = -float('inf')

        for p in my_pieces:
            moves = get_valid_moves(state['pieces'], state['walls'], p['r'], p['c'])
            for m in moves:
                old_r, old_c = p['r'], p['c']
                state['pieces'][p['idx']]['r'] = m['r']
                state['pieces'][p['idx']]['c'] = m['c']
                
                v_walls = get_valid_walls(state['walls'], m['r'], m['c'])
                for w in v_walls:
                    test_wall = {'r': w['r'], 'c': w['c'], 'color': color}
                    state['walls'].append(test_wall)
                    score = evaluate_board(state['pieces'], state['walls'], color) + random.random() * 0.1
                    if score > best_score:
                        best_score = score
                        best_action = {'pIdx': p['idx'], 'mr': m['r'], 'mc': m['c'], 'wr': w['r'], 'wc': w['c']}
                    state['walls'].remove(test_wall)
                
                state['pieces'][p['idx']]['r'] = old_r
                state['pieces'][p['idx']]['c'] = old_c

        if best_action:
            state['pieces'][best_action['pIdx']]['r'] = best_action['mr']
            state['pieces'][best_action['pIdx']]['c'] = best_action['mc']
            state['walls'].append({'r': best_action['wr'], 'c': best_action['wc'], 'color': color})
        else:
            if my_pieces:
                fallback_p = my_pieces[0]
                w_moves = get_valid_walls(state['walls'], fallback_p['r'], fallback_p['c'])
                if w_moves:
                    state['walls'].append({'r': w_moves[0]['r'], 'c': w_moves[0]['c'], 'color': color})
                    
        state['movedPieceIndex'] = -1
        state['selectedPieceIndex'] = -1
        state['stepsTaken'] = 0
        state['phase'] = 'movement'
        state['turnIndex'] = (state['turnIndex'] + 1) % len(state['movementOrder'])

    # 恢復秒數並通知所有人
    state['playerTimes'][color] = 90
    state['version'] = state.get('version', 0) + 1
    check_end_game(room_code)
    socketio.emit('update_board', get_clean_state(state), to=room_code)
    socketio.emit('receive_chat', {'user_name': '系統', 'color': 'yellow', 'message': f'⏳ {color} 逾時，伺服器已強制代為結算。'}, to=room_code)


def check_end_game(room_code):
    """檢查是否遊戲結束（棋規在 engine/rules.py 的 check_game_over）。"""
    state = rooms[room_code]['game_state']
    if state['phase'] == 'placement':
        return
    result = check_game_over(state)
    if result['over']:
        state['phase'] = 'game_over'
        state['territories'] = [[k, c] for k, c in result['territories'].items()]
        if state.get('timer_job'):
            state['timer_job'].kill()


def room_timer_loop(room_code):
    """後端集中倒數計時協程"""
    while True:
        gevent.sleep(1)
        if room_code not in rooms or 'game_state' not in rooms[room_code]:
            break
            
        state = rooms[room_code]['game_state']
        if state['phase'] == 'game_over':
            break
            
        currentColor = state['placementQueue'][state['turnIndex']] if state['phase'] == 'placement' else state['movementOrder'][state['turnIndex']]
        
        state['playerTimes'][currentColor] -= 1
        
        if state['playerTimes'][currentColor] <= 0:
            force_ai_move(room_code)
        else:
            # 每秒同步一次剩餘時間給所有前端
            socketio.emit('sync_time', {'playerTimes': state['playerTimes']}, to=room_code)

def get_clean_state(state):
    """移除不能序列化的協程物件後傳給前端"""
    return {k: v for k, v in state.items() if k != 'timer_job'}
