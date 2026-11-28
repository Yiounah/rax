#!/usr/bin/env bash
# Conda runs this before changing CONDA_SHLVL, including on reactivation.
_rax_deactivate_cuda() {
    local _rax_variable _rax_saved _rax_present
    local _rax_marker="__RAX_CUDA_${CONDA_SHLVL:-0}_SAVED"
    if [[ "${!_rax_marker:-}" == 1 ]]; then
        for _rax_variable in CUDA_HOME CUDA_PATH; do
            _rax_saved="__RAX_CUDA_${CONDA_SHLVL:-0}_${_rax_variable}"
            _rax_present="${_rax_saved}_SET"
            if [[ "${!_rax_present:-}" == 1 ]]; then
                export "$_rax_variable=${!_rax_saved-}"
            else
                unset "$_rax_variable"
            fi
            unset "$_rax_saved" "$_rax_present"
        done
        unset "$_rax_marker"
    fi
}
_rax_deactivate_cuda
unset -f _rax_deactivate_cuda
