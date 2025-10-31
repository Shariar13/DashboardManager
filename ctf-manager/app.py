from flask import Flask, jsonify, send_file, render_template, request, session, redirect, url_for
import subprocess
import os
from functools import wraps
from database import init_db, get_db

app = Flask(__name__)
app.secret_key = 'change-this-to-random-secret-key-for-production'

# Initialize database on startup
init_db()

CHALLENGES = ['bkimminich/juice-shop', 'vulnerables/web-dvwa', 'webgoat/webgoat', 'appsecco/dvja', 'tleemcjr/metasploitable2']
CHALLENGE_NAMES = ['Juice Shop', 'DVWA', 'WebGoat', 'DVJA', 'Metasploitable']
CHALLENGE_PORTS = [3000, 80, 8080, 8080, 22]

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/team-search')
def team_search():
    return render_template('team_search.html')

@app.route('/api/team/search', methods=['POST'])
def search_team():
    data = request.json
    team_code = data.get('team_code', '').strip()
    
    if not team_code:
        return jsonify({'success': False, 'error': 'Please enter team code'}), 400
    
    conn = get_db()
    team = conn.execute('SELECT * FROM teams WHERE team_code=?', (team_code,)).fetchone()
    
    if not team:
        conn.close()
        return jsonify({'success': False, 'error': 'Team not found'}), 404
    
    team_id = team['id']
    team_ip = team['team_ip']
    
    # Get challenge IPs if running
    challenges = []
    if team['challenges_running']:
        containers = conn.execute('SELECT * FROM containers WHERE team_id=? ORDER BY id', (team_id,)).fetchall()
        challenges = [dict(c) for c in containers]
    
    conn.close()
    
    return jsonify({
        'success': True,
        'team': {
            'id': team['id'],
            'name': team['team_name'],
            'code': team['team_code'],
            'team_ip': team_ip,
            'vpn_generated': bool(team['vpn_generated']),
            'challenges_running': bool(team['challenges_running']),
            'vpn_download_url': f'/api/team/{team_id}/vpn/download' if team['vpn_generated'] else None
        },
        'challenges': challenges
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Default credentials
        if username == 'admin' and password == 'ctfadmin123':
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/teams', methods=['GET'])
@login_required
def get_teams():
    conn = get_db()
    teams = conn.execute('SELECT * FROM teams ORDER BY id').fetchall()
    conn.close()
    return jsonify([dict(team) for team in teams])

@app.route('/api/team/add', methods=['POST'])
@login_required
def add_team():
    data = request.json
    team_name = data.get('team_name')
    team_code = data.get('team_code')
    team_ip = data.get('team_ip')
    
    if not team_name or not team_code or not team_ip:
        return jsonify({'success': False, 'error': 'All fields required'}), 400
    
    try:
        team_ip = int(team_ip)
        if team_ip < 1 or team_ip > 254:
            return jsonify({'success': False, 'error': 'Team IP must be between 1-254'}), 400
    except:
        return jsonify({'success': False, 'error': 'Team IP must be a number'}), 400
    
    conn = get_db()
    try:
        cursor = conn.execute('INSERT INTO teams (team_name, team_code, team_ip) VALUES (?,?,?)', 
                             (team_name, team_code, team_ip))
        team_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'team_id': team_id, 
                       'message': f'Team {team_name} added (Team IP: {team_ip})'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/team/<int:team_id>/vpn/generate', methods=['POST'])
@login_required
def generate_vpn(team_id):
    import time
    
    # Get team_ip from database
    conn = get_db()
    team = conn.execute('SELECT team_ip FROM teams WHERE id=?', (team_id,)).fetchone()
    conn.close()
    
    if not team:
        return jsonify({'success': False, 'error': 'Team not found'}), 404
    
    team_ip = team['team_ip']
    
    # Run VPN generation script with team_ip
    result = subprocess.run(
        ['bash', '/app/openvpn/generate-team-vpn.sh', str(team_ip)],
        cwd='/app/openvpn',
        capture_output=True, 
        text=True
    )
    
    time.sleep(2)
    
    vpn_path = f'/app/vpn-configs/team{team_ip}.ovpn'
    
    if os.path.exists(vpn_path):
        conn = get_db()
        conn.execute('UPDATE teams SET vpn_generated=1, vpn_file_path=? WHERE id=?', (vpn_path, team_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'VPN generated successfully'})
    else:
        return jsonify({'success': False, 'error': 'VPN file not created. Check openvpn-server is running.'}), 500

@app.route('/api/team/<int:team_id>/vpn/download')
def download_vpn(team_id):
    conn = get_db()
    team = conn.execute('SELECT vpn_file_path FROM teams WHERE id=?', (team_id,)).fetchone()
    conn.close()
    
    if team and team['vpn_file_path'] and os.path.exists(team['vpn_file_path']):
        return send_file(team['vpn_file_path'], as_attachment=True, download_name=f'team{team_id}.ovpn')
    return jsonify({'error': 'VPN not generated'}), 404

@app.route('/api/team/<int:team_id>/challenges/start', methods=['POST'])
@login_required
def start_challenges(team_id):
    import time
    
    # Get team_ip from database
    conn = get_db()
    team = conn.execute('SELECT team_ip FROM teams WHERE id=?', (team_id,)).fetchone()
    
    if not team:
        conn.close()
        return jsonify({'success': False, 'error': 'Team not found'}), 404
    
    team_ip = team['team_ip']
    
    subnet = f'10.100.{team_ip}.0/24'
    net_name = f'team{team_ip}_net'
    
    # Create network
    subprocess.run(['docker', 'network', 'create', '--subnet', subnet, net_name])
    
    conn.execute('UPDATE teams SET network_created=1 WHERE id=?', (team_id,))
    
    # Start containers
    for i, img in enumerate(CHALLENGES):
        name = f'team{team_ip}_c{i}'
        subprocess.run(['docker', 'run', '-d', '--name', name, '--network', net_name, '-m', '256m', img])
    
    time.sleep(10)
    
    for i, img in enumerate(CHALLENGES):
        name = f'team{team_ip}_c{i}'
        ip = ''
        for attempt in range(5):
            result = subprocess.run(['docker', 'inspect', name, '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'], 
                                  capture_output=True, text=True)
            ip = result.stdout.strip()
            if ip:
                break
            time.sleep(2)
        
        conn.execute('INSERT INTO containers (team_id, container_name, container_id, challenge_type, ip_address, port, status) VALUES (?,?,?,?,?,?,?)',
                    (team_id, name, name, CHALLENGE_NAMES[i], ip if ip else 'pending', CHALLENGE_PORTS[i], 'running'))
    
    conn.execute('UPDATE teams SET challenges_running=1 WHERE id=?', (team_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Challenges started'})

@app.route('/api/team/<int:team_id>/challenges/stop', methods=['POST'])
@login_required
def stop_challenges(team_id):
    conn = get_db()
    team = conn.execute('SELECT team_ip FROM teams WHERE id=?', (team_id,)).fetchone()
    
    if not team:
        conn.close()
        return jsonify({'success': False, 'error': 'Team not found'}), 404
    
    team_ip = team['team_ip']
    
    containers = conn.execute('SELECT container_name FROM containers WHERE team_id=?', (team_id,)).fetchall()
    
    for container in containers:
        subprocess.run(['docker', 'stop', container['container_name']], stderr=subprocess.DEVNULL)
        subprocess.run(['docker', 'rm', container['container_name']], stderr=subprocess.DEVNULL)
    
    subprocess.run(['docker', 'network', 'rm', f'team{team_ip}_net'], stderr=subprocess.DEVNULL)
    
    conn.execute('DELETE FROM containers WHERE team_id=?', (team_id,))
    conn.execute('UPDATE teams SET challenges_running=0, network_created=0 WHERE id=?', (team_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Challenges stopped'})

@app.route('/api/team/<int:team_id>/ips')
@login_required
def get_ips(team_id):
    conn = get_db()
    containers = conn.execute('SELECT * FROM containers WHERE team_id=? ORDER BY id', (team_id,)).fetchall()
    conn.close()
    return jsonify([dict(c) for c in containers])

@app.route('/api/team/<int:team_id>/delete', methods=['POST'])
@login_required
def delete_team(team_id):
    conn = get_db()
    team = conn.execute('SELECT team_ip FROM teams WHERE id=?', (team_id,)).fetchone()
    
    if team:
        team_ip = team['team_ip']
        
        containers = conn.execute('SELECT container_name FROM containers WHERE team_id=?', (team_id,)).fetchall()
        for container in containers:
            subprocess.run(['docker', 'stop', container['container_name']], stderr=subprocess.DEVNULL)
            subprocess.run(['docker', 'rm', container['container_name']], stderr=subprocess.DEVNULL)
        
        subprocess.run(['docker', 'network', 'rm', f'team{team_ip}_net'], stderr=subprocess.DEVNULL)
        
        conn.execute('DELETE FROM containers WHERE team_id=?', (team_id,))
        conn.execute('DELETE FROM teams WHERE id=?', (team_id,))
        conn.commit()
    
    conn.close()
    return jsonify({'success': True, 'message': f'Team {team_id} deleted'})

# System Management Endpoints
@app.route('/api/system/stop-all', methods=['POST'])
@login_required
def stop_all_challenges():
    conn = get_db()
    teams = conn.execute('SELECT id FROM teams WHERE challenges_running=1').fetchall()
    
    for team in teams:
        team_id = team['id']
        containers = conn.execute('SELECT container_name FROM containers WHERE team_id=?', (team_id,)).fetchall()
        
        for container in containers:
            subprocess.run(['docker', 'stop', container['container_name']], stderr=subprocess.DEVNULL)
            subprocess.run(['docker', 'rm', container['container_name']], stderr=subprocess.DEVNULL)
        
        subprocess.run(['docker', 'network', 'rm', f'team{team_id}_net'], stderr=subprocess.DEVNULL)
        
        conn.execute('DELETE FROM containers WHERE team_id=?', (team_id,))
        conn.execute('UPDATE teams SET challenges_running=0, network_created=0 WHERE id=?', (team_id,))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'All challenges stopped'})

@app.route('/api/system/start-all', methods=['POST'])
@login_required
def start_all_challenges():
    conn = get_db()
    teams = conn.execute('SELECT id FROM teams WHERE vpn_generated=1 AND challenges_running=0').fetchall()
    
    for team in teams:
        team_id = team['id']
        try:
            start_challenges_internal(team_id)
        except:
            pass
    
    conn.close()
    return jsonify({'success': True, 'message': f'Started challenges for {len(teams)} teams'})

@app.route('/api/system/generate-all-vpns', methods=['POST'])
@login_required
def generate_all_vpns():
    conn = get_db()
    teams = conn.execute('SELECT id FROM teams WHERE vpn_generated=0').fetchall()
    
    count = 0
    for team in teams:
        team_id = team['id']
        result = subprocess.run(['bash', '/app/openvpn/generate-team-vpn.sh', str(team_id)],
                              cwd='/app/openvpn', capture_output=True, text=True)
        if result.returncode == 0:
            vpn_path = f'/app/vpn-configs/team{team_id}.ovpn'
            if os.path.exists(vpn_path):
                conn.execute('UPDATE teams SET vpn_generated=1, vpn_file_path=? WHERE id=?', (vpn_path, team_id))
                count += 1
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Generated {count} VPN configs'})

@app.route('/api/system/restart', methods=['POST'])
@login_required
def restart_system():
    import threading
    def restart():
        import time
        time.sleep(2)
        subprocess.run(['docker', 'restart', 'ctf-manager'])
    
    threading.Thread(target=restart, daemon=True).start()
    return jsonify({'success': True, 'message': 'Restarting...'})

@app.route('/api/system/status')
@login_required
def system_status():
    # Check OpenVPN
    result = subprocess.run(['docker', 'ps', '--filter', 'name=openvpn-server', '--format', '{{.Names}}'], 
                          capture_output=True, text=True)
    openvpn_running = 'openvpn-server' in result.stdout
    
    # Get stats
    conn = get_db()
    total_teams = conn.execute('SELECT COUNT(*) as count FROM teams').fetchone()['count']
    active_challenges = conn.execute('SELECT COUNT(*) as count FROM teams WHERE challenges_running=1').fetchone()['count']
    total_containers = conn.execute('SELECT COUNT(*) as count FROM containers').fetchone()['count']
    conn.close()
    
    return jsonify({
        'openvpn': openvpn_running,
        'total_teams': total_teams,
        'active_challenges': active_challenges,
        'total_containers': total_containers
    })

def start_challenges_internal(team_id):
    """Internal function to start challenges"""
    import time
    
    conn = get_db()
    team = conn.execute('SELECT team_ip FROM teams WHERE id=?', (team_id,)).fetchone()
    
    if not team:
        conn.close()
        return
    
    team_ip = team['team_ip']
    
    subnet = f'10.100.{team_ip}.0/24'
    net_name = f'team{team_ip}_net'
    
    subprocess.run(['docker', 'network', 'create', '--subnet', subnet, net_name])
    
    conn.execute('UPDATE teams SET network_created=1 WHERE id=?', (team_id,))
    
    for i, img in enumerate(CHALLENGES):
        name = f'team{team_ip}_c{i}'
        subprocess.run(['docker', 'run', '-d', '--name', name, '--network', net_name, '-m', '256m', img])
    
    time.sleep(10)
    
    for i, img in enumerate(CHALLENGES):
        name = f'team{team_ip}_c{i}'
        ip = ''
        for attempt in range(5):
            result = subprocess.run(['docker', 'inspect', name, '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'], 
                                  capture_output=True, text=True)
            ip = result.stdout.strip()
            if ip:
                break
            time.sleep(2)
        
        conn.execute('INSERT INTO containers (team_id, container_name, container_id, challenge_type, ip_address, port, status) VALUES (?,?,?,?,?,?,?)',
                    (team_id, name, name, CHALLENGE_NAMES[i], ip if ip else 'pending', CHALLENGE_PORTS[i], 'running'))
    
    conn.execute('UPDATE teams SET challenges_running=1 WHERE id=?', (team_id,))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)