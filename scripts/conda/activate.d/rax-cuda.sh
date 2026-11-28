#!/usr/bin/env bash
# Scope CUDA to this environment and preserve unset/empty values for deactivation.
_rax_activate_cuda() {
    local _rax_variable _rax_saved _rax_present
    local _rax_marker="__RAX_CUDA_${CONDA_SHLVL:-0}_SAVED"
    if [[ "${!_rax_marker:-}" != 1 ]]; then
        for _rax_variable in CUDA_HOME CUDA_PATH; do
            _rax_saved="__RAX_CUDA_${CONDA_SHLVL:-0}_${_rax_variable}"
            _rax_present="${_rax_saved}_SET"
            if [[ -v $_rax_variable ]]; then
                export "$_rax_present=1"
            else
                export "$_rax_present=0"
            fi
            export "$_rax_saved=${!_rax_variable-}"
        done
        export "$_rax_marker=1"
    fi
    export CUDA_HOME="$CONDA_PREFIX" CUDA_PATH="$CONDA_PREFIX"
}
_rax_activate_cuda
unset -f _rax_activate_cuda
