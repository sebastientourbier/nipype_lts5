# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
    Change directory to provide relative paths for doctests
    >>> import os
    >>> filepath = os.path.dirname( os.path.realpath( __file__ ) )
    >>> datadir = os.path.realpath(os.path.join(filepath, '../../testing/data'))
    >>> os.chdir(datadir)

"""

from nipype.interfaces.base import (BaseInterface, BaseInterfaceInputSpec, traits,
                                    File, TraitedSpec, Directory, OutputMultiPath)
import os, os.path as op
from nipype.utils.misc import package_check
import warnings

from ... import logging
iflogger = logging.getLogger('interface')

import numpy as np
import nibabel as ni
try:
    import scipy.ndimage.morphology as nd
except ImportError:
    raise Exception('Need scipy for binary erosion of white matter and CSF masks')

#have_cmtk = True
#try:
#    package_check('cmtklib')
#except Exception, e:
#    have_cmtk = False
#    warnings.warn('cmtklib not installed')
#else:
from cmtklib.parcellation import (get_parcellation, create_annot_label, 
                                 create_roi, create_wm_mask,
                                 crop_and_move_datasets, generate_WM_and_GM_mask,
                                 crop_and_move_WM_and_GM,create_T1_and_Brain)

def erode_mask(maskFile):
    # Define erosion mask
    imerode = nd.binary_erosion
    se = np.zeros( (3,3,3) )
    se[1,:,1] = 1; se[:,1,1] = 1; se[1,1,:] = 1
    
    # Erode mask
    mask = ni.load( maskFile ).get_data().astype( np.uint32 )
    er_mask = np.zeros( mask.shape )
    idx = np.where( (mask == 1) )
    er_mask[idx] = 1
    er_mask = imerode(er_mask,se)
    er_mask = imerode(er_mask,se)
    img = ni.Nifti1Image(er_mask, ni.load( maskFile ).get_affine(), ni.load( maskFile ).get_header())
    ni.save(img, op.abspath('%s_eroded.nii.gz' % os.path.splitext(op.splitext(op.basename(maskFile))[0])[0]))

class Erode_inputspec(BaseInterfaceInputSpec):
    in_file = File(exists=True)
    
class Erode_outputspec(TraitedSpec):
    out_file = File(exists=True)

class Erode(BaseInterface):
    input_spec = Erode_inputspec
    output_spec = Erode_outputspec

    def _run_interface(self, runtime):
        erode_mask(self.inputs.in_file)
        return runtime
    
    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs['out_file'] = op.abspath('%s_eroded.nii.gz' % os.path.splitext(op.splitext(op.basename(self.inputs.in_file))[0])[0])
        return outputs

class ParcellateInputSpec(BaseInterfaceInputSpec):
    subjects_dir = Directory(desc='Freesurfer main directory')
    subject_id = traits.String(mandatory=True, desc='Subject ID')
    parcellation_scheme = traits.Enum('Lausanne2008',['Lausanne2008','NativeFreesurfer'], usedefault = True)
    erode_masks = traits.Bool(False)


class ParcellateOutputSpec(TraitedSpec):
    #roi_files = OutputMultiPath(File(exists=True),desc='Region of Interest files for connectivity mapping')
    white_matter_mask_file = File(desc='White matter mask file')
    #cc_unknown_file = File(desc='Image file with regions labelled as unknown cortical structures',
    #                exists=True)
    #ribbon_file = File(desc='Image file detailing the cortical ribbon',
    #                exists=True)
    #aseg_file = File(desc='Automated segmentation file converted from Freesurfer "subjects" directory',
    #                exists=True)
    wm_eroded = File(desc="Eroded wm file in original space")
    csf_eroded = File(desc="Eroded csf file in original space")
    brain_eroded = File(desc="Eroded brain file in original space")
    roi_files_in_structural_space = OutputMultiPath(File(exists=True),
                                desc='ROI image resliced to the dimensions of the original structural image')
    T1 = File(desc="T1 image file")
    brain = File(desc="Brain-masked T1 image file")
    brain_mask = File(desc="Brain mask file")


class Parcellate(BaseInterface):
    """Subdivides segmented ROI file into smaller subregions

    This interface interfaces with the ConnectomeMapper Toolkit library
    parcellation functions (cmtklib/parcellation.py) for all
    parcellation resolutions of a given scheme.

    Example
    -------

    >>> import nipype.interfaces.cmtk as cmtk
    >>> parcellate = cmtk.Parcellate()
    >>> parcellate.inputs.subjects_dir = '.'
    >>> parcellate.inputs.subject_id = 'subj1'
    >>> parcellate.run()                 # doctest: +SKIP
    """

    input_spec = ParcellateInputSpec
    output_spec = ParcellateOutputSpec

    def _run_interface(self, runtime):
        #if self.inputs.subjects_dir:
        #   os.environ.update({'SUBJECTS_DIR': self.inputs.subjects_dir})
        iflogger.info("ROI_HR_th.nii.gz / fsmask_1mm.nii.gz CREATION")
        iflogger.info("=============================================")
        
        if self.inputs.parcellation_scheme == "Lausanne2008":
            create_T1_and_Brain(self.inputs.subject_id, self.inputs.subjects_dir)
            create_annot_label(self.inputs.subject_id, self.inputs.subjects_dir)
            create_roi(self.inputs.subject_id, self.inputs.subjects_dir)
            create_wm_mask(self.inputs.subject_id, self.inputs.subjects_dir)
            if self.inputs.erode_masks:
                erode_mask(op.join(self.inputs.subjects_dir,self.inputs.subject_id,'mri','fsmask_1mm.nii.gz'))
                erode_mask(op.join(self.inputs.subjects_dir,self.inputs.subject_id,'mri','csf_mask.nii.gz'))
                erode_mask(op.join(self.inputs.subjects_dir,self.inputs.subject_id,'mri','brainmask.nii.gz'))
            crop_and_move_datasets(self.inputs.subject_id, self.inputs.subjects_dir)
        if self.inputs.parcellation_scheme == "NativeFreesurfer":
            create_T1_and_Brain(self.inputs.subject_id, self.inputs.subjects_dir)
            generate_WM_and_GM_mask(self.inputs.subject_id, self.inputs.subjects_dir)
            if self.inputs.erode_masks:
                erode_mask(op.join(self.inputs.subjects_dir,self.inputs.subject_id,'mri','fsmask_1mm.nii.gz'))
                erode_mask(op.join(self.inputs.subjects_dir,self.inputs.subject_id,'mri','csf_mask.nii.gz'))
                erode_mask(op.join(self.inputs.subjects_dir,self.inputs.subject_id,'mri','brainmask.nii.gz'))
            crop_and_move_WM_and_GM(self.inputs.subject_id, self.inputs.subjects_dir)
            
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()

        outputs['T1'] = op.abspath('T1.nii.gz')
        outputs['brain'] = op.abspath('brain.nii.gz')
        outputs['brain_mask'] = op.abspath('brain_mask.nii.gz')
        
        outputs['white_matter_mask_file'] = op.abspath('fsmask_1mm.nii.gz')
        #outputs['cc_unknown_file'] = op.abspath('cc_unknown.nii.gz')
        #outputs['ribbon_file'] = op.abspath('ribbon.nii.gz')
        #outputs['aseg_file'] = op.abspath('aseg.nii.gz')
        
        #outputs['roi_files'] = self._gen_outfilenames('ROI_HR_th')
        outputs['roi_files_in_structural_space'] = self._gen_outfilenames('ROIv_HR_th')
        
        if self.inputs.erode_masks:
            outputs['wm_eroded'] = op.abspath('wm_eroded.nii.gz')
            outputs['csf_eroded'] = op.abspath('csf_eroded.nii.gz')
            outputs['brain_eroded'] = op.abspath('brainmask_eroded.nii.gz')

        return outputs

    def _gen_outfilenames(self, basename):
        filepaths = []
        for scale in get_parcellation(self.inputs.parcellation_scheme).keys():
            filepaths.append(op.abspath(basename+'_'+scale+'.nii.gz'))
        return filepaths
        
