"""The spm module provides basic functions for interfacing with matlab
and spm to access spm tools.

These functions include:
    
* Realign: within-modality registration

* Coregister: between modality registration
    
* Normalize: non-linear warping to standard space

* Segment: bias correction, segmentation

* Smooth: smooth with Gaussian kernel

"""
__docformat__ = 'restructuredtext'

# Standard library imports
from glob import glob
from copy import deepcopy

# Third-party imports
import numpy as np

# Local imports
from nipype.interfaces.spm import (SpmMatlabCommandLine, scans_for_fname,
                                   scans_for_fnames)
from nipype.interfaces.spm import (NEW_SPMCommand, scans_for_fname,
                                   scans_for_fnames, logger)
from nipype.interfaces.base import Bunch

from nipype.interfaces.base import TraitedSpec, traits

from nipype.utils.filemanip import (fname_presuffix, filename_to_list, 
                                    list_to_filename, FileNotFoundError)
from nipype.utils.spm_docs import grab_doc



class SliceTiming(SpmMatlabCommandLine):
    """Use spm to perform slice timing correction.

    See SliceTiming().spm_doc() for more information.

    Examples
    --------

    >>> from nipype.interfaces.spm import SliceTiming
    >>> st = SliceTiming()
    >>> st.inputs.infile = 'func.nii'
    >>> st.inputs.num_slices = 32
    >>> st.inputs.time_repetition = 6.0
    >>> st.inputs.time_acquisition = 6. - 6./32.
    >>> st.inputs.slice_order = range(32,0,-1)
    >>> st.inputs.ref_slice = 1
    """

    def spm_doc(self):
        """Print out SPM documentation."""
        print grab_doc('SliceTiming')
    
    @property
    def cmd(self):
        return 'spm_st'

    @property
    def jobtype(self):
        return 'temporal'

    @property
    def jobname(self):
        return 'st'

    opt_map = {'infile': ('scans',
                          'list of filenames to apply slice timing'),
               'num_slices': ('nslices',
                              'number of slices in a volume'),
               'time_repetition': ('tr',
                                   'time between volume acquisitions ' \
                                       '(start to start time)'),
               'time_acquisition': ('ta',
                                    'time of volume acquisition. usually ' \
                                        'calculated as TR-(TR/num_slices)'),
               'slice_order': ('so',
                               '1-based order in which slices are acquired'),
               'ref_slice': ('refslice',
                             '1-based Number of the reference slice')
               }
        
    def get_input_info(self):
        """ Provides information about inputs as a dict
            info = [Bunch(key=string,copy=bool,ext='.nii'),...]
        """
        info = [Bunch(key='infile',copy=False)]
        return info

    def _convert_inputs(self, opt, val):
        """Convert input to appropriate format for spm
        """
        if opt == 'infile':
            return scans_for_fnames(filename_to_list(val),
                                    separate_sessions=True)
        return val

    def run(self, infile=None, **inputs):
        """Executes the SPM slice timing function using MATLAB
        
        Parameters
        ----------
        
        infile: string, list
            image file(s) to smooth
        """
        if infile:
            self.inputs.infile = infile
        if not self.inputs.infile:
            raise AttributeError('Slice timing requires a file')
        self.inputs.update(**inputs)
        return super(SliceTiming,self).run()

    out_map = {'timecorrected_files' : ('slice time corrected files','infile')}
        
    def aggregate_outputs(self):
        outputs = self.outputs()
        outputs.timecorrected_files = []
        filelist = filename_to_list(self.inputs.infile)
        for f in filelist:
            s_file = glob(fname_presuffix(f, prefix='a'))
            assert len(s_file) == 1, 'No slice time corrected file generated by SPM Slice Timing'
            outputs.timecorrected_files.append(s_file[0])
        return outputs
    

class Realign(NEW_SPMCommand):
    """Use spm_realign for estimating within modality rigid body alignment

    Examples
    --------

    >>> import nipype.interfaces.spm as spm
    >>> realign = spm.Realign()
    >>> realign.inputs.infile = 'a.nii'
    >>> realign.inputs.register_to_mean = True
    >>> realign.run() # doctest: +SKIP

    """

    @property
    def jobtype(self):
         return 'spatial'

    @property
    def jobname(self):
        return 'realign'

    class input_spec(TraitedSpec):
        infile = traits.List(traits.File(exists=True), field='data', mandatory=True,
                             desc='list of filenames to realign', copyfile=True)
        jobtype = traits.Enum('estwrite', 'estimate', 'write',
                              desc='one of: estimate, write, estwrite',
                              usedefault=True)
        quality = traits.Range(low=0.0, high=1.0, field = 'eoptions.quality',
                               desc = '0.1 = fast, 1.0 = precise')
        fwhm = traits.Range(low=0.0, field = 'eoptions.fwhm',
                            desc = 'gaussian smoothing kernel width')
        separation = traits.Range(low=0.0, field = 'eoptions.sep',
                                  desc = 'sampling separation in mm')
        register_to_mean = traits.Bool(field='eoptions.rtm',
                 desc='Indicate whether realignment is done to the mean image')
        weight_img = traits.File(exists=True, field='eoptions.weight',
                                 desc='filename of weighting image')
        interp = traits.Range(low=0, high=7, field='eoptions.interp',
                   desc='degree of b-spline used for interpolation')
        wrap = traits.List(traits.Int, field='eoptions.wrap', min_len=3, max_len=3,
                      desc='Check if interpolation should wrap in [x,y,z]')
        write_which = traits.List(traits.Int, field='roptions.which',
                                  min_len=2, max_len=2,
                                  desc = 'determines which images to reslice')
        write_interp = traits.Range(low=0, high=7, field='roptions.interp',
                             desc='degree of b-spline used for interpolation')
        write_wrap = traits.List(traits.Int, field='eoptions.wrap',
                                 min_len=3, max_len=3,
                      desc='Check if interpolation should wrap in [x,y,z]')
        write_mask = traits.Bool(field='roptions.mask',
                                 desc='True/False mask output image')

    class output_spec(TraitedSpec):
        mean_image = traits.File(exists=True,
                                 desc='Mean image file from the realignment')
        realigned_files = traits.List(traits.File, desc='Realigned files')
        realignment_parameters = traits.List(traits.File,
                          desc='Estimated translation and rotation parameters')

    def _format_arg(self, opt, val):
        """Convert input to appropriate format for spm
        """
        if opt == 'infile':
            return scans_for_fnames(filename_to_list(val),
                                    keep4d=True,
                                    separate_sessions=True)
        if opt == 'register_to_mean': # XX check if this is necessary
            return int(val)
        return val
    
    def _parse_inputs(self):
        """validate spm realign options if set to None ignore
        """
        einputs = super(Realign, self)._parse_inputs(skip=('jobtype'))
        jobtype =  self.inputs.jobtype
        return [{'%s'%(jobtype):einputs[0]}]

    def _list_outputs(self):
        outputs = self._outputs()._dictcopy()
        outputs['mean_image'] = fname_presuffix(self.inputs.infile[0], prefix='mean')
        if self.inputs.jobtype == "write" or self.inputs.jobtype == "estwrite":
            for imgf in self.inputs.infile:
                outputs['realigned_files'].append(fname_presuffix(imgf, prefix='r'))
                outputs['realignment_parameters'].append(fname_presuffix(imgf,
                                                                   prefix='rp_',
                                                                   suffix='.txt',
                                                                   use_ext=False))
        return outputs
        
class Coregister(NEW_SPMCommand):
    """Use spm_coreg for estimating cross-modality rigid body alignment

    Examples
    --------
    
    >>> import nipype.interfaces.spm as spm
    >>> coreg = spm.Coregister()
    >>> coreg.inputs.target = 'a.nii'
    >>> coreg.inputs.source = 'b.nii'
    >>> coreg.run() # doctest: +SKIP
    
    """
    
    @property
    def jobtype(self):
        return 'spatial'

    @property
    def jobname(self):
        return 'coreg'
    
    class input_spec(TraitedSpec):
        target = traits.File(exists=True, field='ref', mandatory=True,
                             desc='reference file to register to')
        source = traits.List(traits.File(exists=True), field='source',
                             desc='file to register to target', copyfile=True)
        jobtype = traits.Enum('estwrite','estimate', 'write',
                              desc='one of: estimate, write, estwrite',
                              usedefault=True)
        apply_to_files = traits.List(traits.File(exists=True), field='other',
                                     desc='files to apply transformation to', copyfile=True)
        cost_function = traits.Enum('mi', 'nmi', 'ecc', 'ncc', field = 'eoptions.cost_fun',
                                    desc = "cost function, one of: 'mi' - Mutual Information, " +
                                    "'nmi' - Normalised Mutual Information, 'ecc' - Entropy Correlation Coefficient, " +
                                    "'ncc' - Normalised Cross Correlation")
        fwhm = traits.Float(field = 'eoptions.fwhm', desc = 'gaussian smoothing kernel width')
        separation = traits.List(traits.Float(), field = 'eoptions.sep', desc = 'sampling separation in mm')
        tolerance =  traits.List(traits.Float(), field = 'eoptions.tol',
                                  desc = 'acceptable tolerance for each of 12 params')
        write_interp = traits.Range(low = 0, hign = 7, field = 'roptions.interp',
                                    desc = 'degree of b-spline used for interpolation')
        write_wrap = traits.List(traits.Bool(), min_len = 3, max_len = 3, field = 'roptions.wrap',
                                 desc = 'Check if interpolation should wrap in [x,y,z]')
        write_mask = traits.Bool(field = 'roptions.mask',
                                 desc = 'True/False mask output image')
        
    class output_spec(TraitedSpec):
        coregistered_source = traits.List(traits.File(exists=True), desc = 'Coregistered source files')
        coregistered_files = traits.List(traits.File, desc = 'Coregistered other files')
    
    
    def _parse_inputs(self):
        """validate spm coregister options if set to None ignore
        """
        einputs = super(Coregister, self)._parse_inputs(skip=('jobtype'))
        jobtype =  self.inputs.jobtype
        return [{'%s'%(jobtype):einputs[0]}]
    
    def _list_outputs(self):
        outputs = self._outputs()._dictcopy()
        
        if self.inputs.jobtype == "estimate":
            if self.inputs.apply_to_files != None:
                outputs.coregistered_files = self.inputs.apply_to_files
            outputs.coregistered_source = self.inputs.source
        elif self.inputs.jobtype == "write" or self.inputs.jobtype == "estwrite":
            if self.inputs.apply_to_files != None:
                for imgf in self.inputs.apply_to_files:
                    outputs['coregistered_files'].append(fname_presuffix(imgf, prefix='r'))
                    
            for imgf in self.inputs.source:
                outputs['coregistered_source'].append(fname_presuffix(imgf, prefix='r'))
                
        return outputs

class Normalize(SpmMatlabCommandLine):
    """use spm_normalise for warping an image to a template

    Examples
    --------
    
    """
    
    def spm_doc(self):
        """Print out SPM documentation."""
        print grab_doc('Normalise: Estimate & Write')

    @property
    def cmd(self):
        return 'spm_normalise'

    @property
    def jobtype(self):
        return 'spatial'

    @property
    def jobname(self):
        return 'normalise'
    
    opt_map = {'template': ('eoptions.template', 'template file to normalize to'),
               'source': ('subj.source', 'file to normalize to template'),
               'jobtype': (None, 'one of: estimate, write, estwrite (opt, estwrite)', 'estwrite'),
               'apply_to_files': ('subj.resample',
                                  'files to apply transformation to (opt,)'),
               'parameter_file': ('subj.matname',
                                  'normalization parameter file*_sn.mat'),
               'source_weight': ('subj.wtsrc',
                                 'name of weighting image for source (opt)'),
               'template_weight': ('eoptions.weight',
                                   'name of weighting image for template (opt)'),
               'source_image_smoothing': ('eoptions.smosrc',
                                          'source smoothing (opt)'),
               'template_image_smoothing': ('eoptions.smoref',
                                            'template smoothing (opt)'),
               'affine_regularization_type': ('eoptions.regype',
                                              'mni, size, none (opt)'),
               'DCT_period_cutoff': ('eoptions.cutoff',
                                     'Cutoff of for DCT bases (opt, 25)'),
               'nonlinear_iterations': ('eoptions.nits',
                     'Number of iterations of nonlinear warping (opt, 16)'),
               'nonlinear_regularization': ('eoptions.reg',
                                            'min = 0; max = 1 (opt, 1)'),
               'write_preserve': ('roptions.preserve',
                     'True/False warped images are modulated (opt, False)'),
               'write_bounding_box': ('roptions.bb', '6-element list (opt,)'),
               'write_voxel_sizes': ('roptions.vox', '3-element list (opt,)'),
               'write_interp': ('roptions.interp',
                           'degree of b-spline used for interpolation (opt, 0)'),
               'write_wrap': ('roptions.wrap',
                        'Check if interpolation should wrap in [x,y,z] (opt, [0,0,0])'),
               }

    def get_input_info(self):
        """ Provides information about inputs as a dict
            info = [Bunch(key=string,copy=bool,ext='.nii'),...]
        """
        info = [Bunch(key='source',copy=False),
                Bunch(key='parameter_file',copy=False),
                Bunch(key='apply_to_files',copy=False)]
        return info
        
    def _convert_inputs(self, opt, val):
        """Convert input to appropriate format for spm
        """
        if opt == 'template':
            return scans_for_fname(filename_to_list(val))
        if opt == 'source':
            return scans_for_fname(filename_to_list(val))
        if opt == 'apply_to_files':
            return scans_for_fnames(filename_to_list(val))
        if opt == 'parameter_file':
            return np.array([list_to_filename(val)],dtype=object)
        if opt in ['write_wrap']:
            if len(val) != 3:
                raise ValueError('%s must have 3 elements'%opt)
        return val

    def _parse_inputs(self):
        """validate spm realign options if set to None ignore
        """
        einputs = super(Normalize, self)._parse_inputs(skip=('jobtype',
                                                             'apply_to_files'))
        if self.inputs.apply_to_files:
            inputfiles = deepcopy(filename_to_list(self.inputs.apply_to_files))
            if self.inputs.source:
                inputfiles.append(list_to_filename(self.inputs.source))
            einputs[0]['subj']['resample'] = scans_for_fnames(inputfiles)
        jobtype =  self.inputs.jobtype
        if jobtype in ['estwrite', 'write']:
            if self.inputs.apply_to_files is None:
                if self.inputs.source:
                    einputs[0]['subj']['resample'] = scans_for_fname(self.inputs.source)            
        return [{'%s'%(jobtype):einputs[0]}]

    def run(self, template=None, source=None, parameter_file=None, apply_to_files=None, **inputs):
        """Executes the SPM normalize function using MATLAB
        
        Parameters
        ----------
        
        template: string, list containing 1 filename
            template image file to normalize to
        source: source image file that is normalized
            to template.
        """
        if template:
            self.inputs.template = template
        if source:
            self.inputs.source = source
        if parameter_file:
            self.inputs.parameter_file = parameter_file
        if apply_to_files:
            self.inputs.apply_to_files = apply_to_files
            
        jobtype =  self.inputs.jobtype
        if jobtype.startswith('est'):
            if not self.inputs.template:
                raise AttributeError('Normalize estimation requires a target file')
            if not self.inputs.source:
                raise AttributeError('Realign requires a source file')
        else:
            if not self.inputs.apply_to_files:
                raise AttributeError('Normalize write requires a files to apply')
            if not self.inputs.parameter_file:
                raise AttributeError('Normalize write requires a transformation matrix')
            
        self.inputs.update(**inputs)
        return super(Normalize,self).run()
    

    out_map = {'normalization_parameters' : ('MAT file containing the normalization parameters',),
               'normalized_source' : ('Normalized source file',),
               'normalized_files' : ('Normalized other files',
                                     'apply_to_files')
               }
        
    def aggregate_outputs(self):
           
        outputs = self.outputs()
        jobtype =  self.inputs.jobtype
        if jobtype.startswith('est'):
            sourcefile = list_to_filename(self.inputs.source)
            n_param = glob(fname_presuffix(sourcefile,suffix='_sn.mat',use_ext=False))
            assert len(n_param) == 1, 'No normalization parameter files '\
                'generated by SPM Normalize'
            outputs.normalization_parameters = n_param
        outputs.normalized_files = []
        if self.inputs.source is not None:
            if isinstance(self.inputs.source, list):
                source_ext = self.inputs.source[0][-4:]
            else:
                source_ext = self.inputs.source[-4:]
                
            sourcefile = list_to_filename(self.inputs.source)
            n_source = glob(fname_presuffix(sourcefile,prefix='w',suffix=source_ext,use_ext=False))
            outputs.normalized_source = list_to_filename(n_source)
        if self.inputs.apply_to_files is not None:
            if isinstance(self.inputs.apply_to_files, list):
                files_ext = self.inputs.apply_to_files[0][-4:]
            else:
                files_ext = self.inputs.apply_to_files[-4:]
                
            filelist = filename_to_list(self.inputs.apply_to_files)
            for f in filelist:
                n_file = glob(fname_presuffix(f,prefix='w',suffix=files_ext,use_ext=False))
                assert len(n_file) == 1, 'No normalized file %s generated by SPM Normalize'%n_file
                outputs.normalized_files.append(n_file[0])
        outputs.normalized_files = list_to_filename(outputs.normalized_files)
        return outputs
        
class Segment(SpmMatlabCommandLine):
    """use spm_segment to separate structural images into different
    tissue classes.

    Examples
    --------
    
    """
    
    def spm_doc(self):
        """Print out SPM documentation."""
        print grab_doc('Segment')
    
    @property
    def cmd(self):
        return 'spm_segment'

    @property
    def jobtype(self):
        return 'spatial'

    @property
    def jobname(self):
        return 'preproc'

    #Options to produce grey matter images: c1*.img, wc1*.img and
    #mwc1*.img. None: [0,0,0], Native Space: [0,0,1], Unmodulated Normalised:
    #[0,1,0], Modulated Normalised: [1,0,0], Native + Unmodulated Normalised:
    #[0,1,1], Native + Modulated Normalised: [1,0,1], Native + Modulated +
    #Unmodulated: [1,1,1], Modulated + Unmodulated Normalised: [1,1,0]
    
    opt_map = {'data': ('data', 'one scan per subject'),
               'gm_output_type': ('output.GM', '3-element list (opt,)'),
               'wm_output_type': ('output.WM', '3-element list (opt,)'),
               'csf_output_type': ('output.CSF', '3-element list (opt,)'),
               'save_bias_corrected': ('output.biascor',
                     'True/False produce a bias corrected image (opt, )'),
               'clean_masks': ('output.cleanup',
                     'clean using estimated brain mask 0(no)-2 (opt, )'),
               'tissue_prob_maps': ('opts.tpm',
                     'list of gray, white & csf prob. (opt,)'),
               'gaussians_per_class': ('opts.ngaus',
                     'num Gaussians capture intensity distribution (opt,)'),
               'affine_regularization': ('opts.regtype',
                      'mni, eastern, subj, none (opt,)'),
               'warping_regularization': ('opts.warpreg',
                      'Controls balance between parameters and data (opt, 1)'),
               'warp_frequency_cutoff': ('opts.warpco', 'Cutoff of DCT bases (opt,)'),
               'bias_regularization': ('opts.biasreg',
                      'no(0) - extremely heavy (10), (opt, )'),
               'bias_fwhm': ('opts.biasfwhm',
                      'FWHM of Gaussian smoothness of bias (opt,)'),
               'sampling_distance': ('opts.samp',
                      'Sampling distance on data for parameter estimation (opt,)'),
               'mask_image': ('opts.msk',
                      'Binary image to restrict parameter estimation (opt,)'),
               }

    def get_input_info(self):
        """ Provides information about inputs as a dict
            info = [Bunch(key=string,copy=bool,ext='.nii'),...]
        """
        info = [Bunch(key='data',copy=False)]
        return info
    
    def _convert_inputs(self, opt, val):
        """Convert input to appropriate format for spm
        """
        if opt in ['data', 'tissue_prob_maps']:
            if isinstance(val, list):
                return scans_for_fnames(val)
            else:
                return scans_for_fname(val)
        if opt == 'save_bias_corrected':
            return int(val)
        if opt == 'mask_image':
            return scans_for_fname(val)
        return val

    def run(self, data=None, **inputs):
        """Executes the SPM segment function using MATLAB
        
        Parameters
        ----------
        
        data: string, list
            image file to segment
        """
        if data:
            self.inputs.data = data
        if not self.inputs.data:
            raise AttributeError('Segment requires a data file')
        self.inputs.update(**inputs)
        return super(Segment,self).run()

    out_map = {'native_class_images' : ('native images for the 3 tissue types',),
               'normalized_class_images' : ('normalized images',),
               'modulated_class_images' : ('modulated, normalized images',),
               'native_gm_image' : ('native space grey probability map',),
               'normalized_gm_image' : ('normalized grey probability map',),
               'modulated_gm_image' : ('modulated, normalized grey probability map',),
               'native_wm_image' : ('native space white probability map',),
               'normalized_wm_image' : ('normalized white probability map',),
               'modulated_wm_image' : ('modulated, normalized white probability map',),
               'native_csf_image' : ('native space csf probability map',),
               'normalized_csf_image' : ('normalized csf probability map',),
               'modulated_csf_image' : ('modulated, normalized csf probability map'),
               'modulated_input_image' : ('modulated version of input image',),
               'transformation_mat' : ('Normalization transformation',),
               'inverse_transformation_mat' : ('Inverse normalization info',),
               }
        
    def aggregate_outputs(self):
        outputs = self.outputs()
        f = self.inputs.data
        files_ext = f[0][-4:]
        m_file = glob(fname_presuffix(f,prefix='m',suffix=files_ext,use_ext=False))
        outputs.modulated_input_image = m_file
        c_files = glob(fname_presuffix(f,prefix='c*',suffix=files_ext,use_ext=False))
        outputs.native_class_images = c_files
        wc_files = glob(fname_presuffix(f,prefix='wc*',suffix=files_ext,use_ext=False))
        outputs.normalized_class_images = wc_files
        mwc_files = glob(fname_presuffix(f,prefix='mwc*',suffix=files_ext,use_ext=False))
        outputs.modulated_class_images = mwc_files
        
        c_files = glob(fname_presuffix(f,prefix='c1',suffix=files_ext,use_ext=False))
        outputs.native_gm_image = c_files
        wc_files = glob(fname_presuffix(f,prefix='wc1',suffix=files_ext,use_ext=False))
        outputs.normalized_gm_image = wc_files
        mwc_files = glob(fname_presuffix(f,prefix='mwc1',suffix=files_ext,use_ext=False))
        outputs.modulated_gm_image = mwc_files
        
        c_files = glob(fname_presuffix(f,prefix='c2',suffix=files_ext,use_ext=False))
        outputs.native_wm_image = c_files
        wc_files = glob(fname_presuffix(f,prefix='wc2',suffix=files_ext,use_ext=False))
        outputs.normalized_wm_image = wc_files
        mwc_files = glob(fname_presuffix(f,prefix='mwc2',suffix=files_ext,use_ext=False))
        outputs.modulated_wm_image = mwc_files
        
        c_files = glob(fname_presuffix(f,prefix='c3',suffix=files_ext,use_ext=False))
        outputs.native_csf_image = c_files
        wc_files = glob(fname_presuffix(f,prefix='wc3',suffix=files_ext,use_ext=False))
        outputs.normalized_csf_image = wc_files
        mwc_files = glob(fname_presuffix(f,prefix='mwc3',suffix=files_ext,use_ext=False))
        outputs.modulated_csf_image = mwc_files
        
        t_mat = glob(fname_presuffix(f,suffix='_seg_sn.mat',use_ext=False))
        outputs.transformation_mat = t_mat
        invt_mat = glob(fname_presuffix(f,suffix='_seg_inv_sn.mat',use_ext=False))
        outputs.inverse_transformation_mat = invt_mat
        return outputs

class Smooth(SpmMatlabCommandLine):
    """use spm_smooth for 3D Gaussian smoothing of image volumes.

    Examples
    --------
    
    """

    def spm_doc(self):
        """Print out SPM documentation."""
        print grab_doc('Smooth')
    
    @property
    def cmd(self):
        return 'spm_smooth'

    @property
    def jobtype(self):
        return 'spatial'

    @property
    def jobname(self):
        return 'smooth'

    opt_map = {'infile': ('data', 'list of files to smooth'),
              'fwhm': ('fwhm', '3-list of fwhm for each dimension (opt, 8)'),
              'data_type': ('dtype', 'Data type of the output images (opt, 0)'),
              }
    
    def get_input_info(self):
        """ Provides information about inputs as a dict
            info = [Bunch(key=string,copy=bool,ext='.nii'),...]
        """
        info = [Bunch(key='infile',copy=False)]
        return info
        
    def _convert_inputs(self, opt, val):
        """Convert input to appropriate format for spm
        """
        if opt in ['infile']:
            return scans_for_fnames(filename_to_list(val))
        if opt == 'fwhm':
            if not isinstance(val, list):
                return [val,val,val]
            if isinstance(val, list):
                if len(val) == 1:
                    return [val[0],val[0],val[0]]
                else:
                    return val
        return val

    def run(self, infile=None, **inputs):
        """Executes the SPM smooth function using MATLAB
        
        Parameters
        ----------
        
        infile: string, list
            image file(s) to smooth
        """
        if infile:
            self.inputs.infile = infile
        if not self.inputs.infile:
            raise AttributeError('Smooth requires a file')
        self.inputs.update(**inputs)
        return super(Smooth,self).run()

    out_map = {'smoothed_files' : ('smoothed files',)}
    
    def aggregate_outputs(self):
        outputs = self.outputs()
        outputs.smoothed_files = []
        filelist = filename_to_list(self.inputs.infile)
        if filelist:
            files_ext = filelist[0][-4:]
        for f in filelist:
            s_file = glob(fname_presuffix(f, prefix='s', suffix=files_ext, use_ext=False))
            assert len(s_file) == 1, 'No smoothed file generated by SPM Smooth'
            outputs.smoothed_files.append(s_file[0])
        return outputs

###################################
#
# NEW_ classes
#
###################################

