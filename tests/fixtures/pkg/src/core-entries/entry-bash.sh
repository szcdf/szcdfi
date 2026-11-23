export SZCDF_CONFIG_ROOT="${HOME}/.config/szcdf"
if [ -f "${SZCDF_CONFIG_ROOT}/_bootstrap.sh" ]; then
  . "${SZCDF_CONFIG_ROOT}/_bootstrap.sh"
fi
