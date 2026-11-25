#!/usr/bin/env bash
# Start one simulator, check RGB-D cameras and step the robot without model calls.
set -eo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$PROJECT_ROOT/runtime/miniforge3/etc/profile.d/conda.sh"
conda activate "$(readlink -f "$PROJECT_ROOT/runtime/envs/robodojo")"
export CUDA_PATH="$CONDA_PREFIX" PYTHONNOUSERSITE=1
source "$PROJECT_ROOT/scripts/robodojo_env.sh"
set -u
cd "$ROBODOJO_PROJECT_ROOT"
exec "$ROBODOJO_PYTHON" - "$@" <<'PY'
import argparse
import json
import importlib.metadata
import os
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image
from services.robodojo.mcp_server import SimulatorProcess

parser = argparse.ArgumentParser(description='Single-simulator RoboDojo smoke check')
parser.add_argument('--gpu', default='0')
parser.add_argument('--task', default='make_kong')
parser.add_argument('--startup-timeout', type=float, default=900)
parser.add_argument('--skip-planner', action='store_true')
args = parser.parse_args()
assert importlib.metadata.version('isaacsim') == '6.0.1.0', 'Activate the Isaac Sim 6 compatibility environment'
project = Path(os.environ['ROBODOJO_PROJECT_ROOT'])
parent = (project / 'runtime/integration-tests').resolve()
parent.mkdir(parents=True, exist_ok=True)
output = Path(tempfile.mkdtemp(prefix='robodojo-smoke-', dir=parent))
sim = SimulatorProcess(project_root=project, python=os.environ['ROBODOJO_PYTHON'], output_root=output)
print(f'Artifacts: {output}', flush=True)
try:
    sim.start(task=args.task, seed=0, eval_seed=0, run_id='smoke',
              sim_gpu=args.gpu, sim_port=0, startup_timeout=args.startup_timeout,
              enable_depth=True, enable_camera_parameters=True)
    initial = sim.request('teacher_observation')
    states = np.asarray(initial['states'])
    assert states.shape == (14,) and np.isfinite(states).all(), states
    result = sim.request('chunk_step', actions=[states.tolist()] * 3)
    sim.step_id = result['step_id']
    assert len(result['frames']) == 3, 'Expected three executed simulation steps'
    observation = result['frames'][-1]
    cameras = {}
    for camera in ('cam_high', 'cam_left_wrist', 'cam_right_wrist'):
        rgb = np.asarray(observation[camera])[..., :3]
        depth = np.asarray(observation[f'{camera}_depth_m'])
        assert rgb.ndim == 3 and rgb.dtype == np.uint8 and rgb.std() > 1, camera
        assert depth.shape[:2] == rgb.shape[:2], camera
        valid = np.isfinite(depth) & (depth > 0)
        assert valid.any(), camera
        Image.fromarray(rgb).save(output / f'{camera}.png')
        cameras[camera] = {'rgb_shape': list(rgb.shape), 'valid_depth_pixels': int(valid.sum())}
    target_joints = np.asarray(observation['states']).copy()
    start_joint = float(target_joints[0])
    target_joints[0] += 0.04
    moved = sim.request('chunk_step', actions=[target_joints.tolist()] * 15)
    sim.step_id = moved['step_id']
    observation = moved['frames'][-1]
    measured = np.asarray(observation['states'])
    tracking_error = float(abs(measured[0] - target_joints[0]))
    assert abs(measured[0] - start_joint) > 0.005, 'Command did not move the physical joint'
    assert tracking_error < 0.025, ('Joint tracking error', tracking_error)
    fk = sim.request('fk_preview', actions=[measured.tolist()] * 50)
    assert fk['measured_fk_check']['passed'], fk
    print('RGB-D, physical joint movement and measured FK passed', flush=True)
    planning = {'status': 'skipped'}
    if not args.skip_planner:
        # Generate a reachable nearby goal from FK, including at full extension.
        planned_joints = measured.copy()
        planned_joints[0] += 0.03
        goal_fk = sim.request('fk_preview', actions=[planned_joints.tolist()] * 50)
        target = dict(goal_fk['trajectory'][0]['left'])
        target.pop('gripper_closed')
        print('Checking cuRobo planning and execution', flush=True)
        planned = sim.request('free_space_move', arm='left', target=target, preview_only=True)
        assert planned['status'] == 'Success', planned
        executed = sim.request('execute_motion_plan', motion_plan_id=planned['motion_plan_id'])
        sim.step_id = executed['step_id']
        assert executed['status'] == 'Success' and executed['goal_reached'], {
            k: v for k, v in executed.items() if k not in ('frames', 'steps')}
        planning = {'status': 'passed', 'executed_control_blocks': executed['executed_control_blocks'],
                    'measured_goal_error': executed['measured_goal_error']}
    report = {'task': args.task, 'gpu': args.gpu, 'steps': sim.step_id, 'joint_count': len(states),
              'cameras': cameras, 'joint_tracking_error_rad': tracking_error,
              'measured_fk': fk['measured_fk_check'], 'planning': planning, 'status': 'passed'}
    report['artifacts'] = str(output)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    (project / 'runtime/checks/isaac6-smoke-report.json').write_text(json.dumps(report, indent=2) + '\n')
    sim.finish('Environment smoke check completed')
    print(json.dumps(report, indent=2), flush=True)
finally:
    sim.stop()
PY
