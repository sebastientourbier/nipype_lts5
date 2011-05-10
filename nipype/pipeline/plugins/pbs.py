"""Parallel workflow execution via PBS/Torque
"""

import os

from .base import (SGELikeBatchManagerBase, logger)

from nipype.interfaces.base import CommandLine

class PBSPlugin(SGELikeBatchManagerBase):
    """Execute using PBS/Torque

    The plugin_args input to run can be used to control the SGE execution.
    Currently supported options are:

    - template : template to use for batch job submission
    - qsub_args : arguments to be prepended to the job execution script in the
                  qsub call

    """

    def __init__(self, **kwargs):
        template="""
            #PBS -V
            #PBS -S /bin/sh
            """
        super(PBSPlugin, self).__init__(template, **kwargs)

    def _is_pending(self, taskid):
        cmd = CommandLine('qstat')
        cmd.inputs.args = '-j %d'%taskid
        # check pbs task
        result = cmd.run()
        if result.runtime.stdout.startswith('='):
            return True
        return False

    def _submit_batchtask(self, scriptfile):
        cmd = CommandLine('qsub', environ=os.environ.data)
        qsubargs = ''
        if self._qsub_args:
            qsubargs = self._qsub_args
        cmd.inputs.args = '%s %s'%(qsubargs, scriptfile)
        result = cmd.run()

        # retrieve pbs taskid
        if not result.runtime.returncode:
            taskid = int(result.runtime.stdout.split(' ')[2])
            self._pending[taskid] = node.output_dir()
            logger.debug('submitted pbs task: %d for node %s'%(taskid, node._id))
        else:
            raise RuntimeError('\n'.join(('Could not submit pbs task for node %s'%node._id,
                                          result.runtime.stderr)))
        return taskid
