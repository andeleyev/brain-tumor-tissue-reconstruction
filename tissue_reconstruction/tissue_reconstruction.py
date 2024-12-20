
import ants
import os
import numpy as np
import shutil
import tempfile
import pathlib


# Static Variables

current_dir = os.path.dirname(os.path.abspath(__file__))

_atlas_t1_path = os.path.join(current_dir, "data", "sub-mni152_t1-inside-brain_space-sri.nii.gz")

_atlas_tissue_segmentation_path = os.path.join(current_dir, "data", "sub-mni152_tissue-with-antsN4_space-sri.nii.gz")
_atlas_wm_pMap_path = os.path.join(current_dir, "data", "sub-mni152_tissue-with-antsN4_wm_space-sri.nii.gz")
_atlas_gm_pMap_path = os.path.join(current_dir, "data", "sub-mni152_tissue-with-antsN4_gm_space-sri.nii.gz")
_atlas_csf_pMap_path = os.path.join(current_dir, "data", "sub-mni152_tissue-with-antsN4_csf_space-sri.nii.gz")

_atlas_fiber_FA_path = os.path.join(current_dir, "data", "FSL_HCP1065_FA_1mm_space-sri.nii.gz")
_atlas_fiber_DTI_path = os.path.join(current_dir, "data", "FSL_HCP1065_tensor_1mm_space-HPC-AntsIndexSpace_SRI.nii.gz")

# Loading the Images
atlas_t1_img = ants.image_read(_atlas_t1_path)

atlas_tissue_segmentation = ants.image_read(_atlas_tissue_segmentation_path)
atlas_wm_pMap = ants.image_read(_atlas_wm_pMap_path)
atlas_gm_pMap = ants.image_read(_atlas_gm_pMap_path)
atlas_csf_pMap = ants.image_read(_atlas_csf_pMap_path)

atlas_fiber_tracts_FA = ants.image_read(_atlas_fiber_FA_path)
atlas_fiber_tracts_DTI = ants.image_read(_atlas_fiber_DTI_path)



def register_atlas(fixed_image, atlas):

    reg = ants.registration(fixed=fixed_image, moving=atlas, type_of_transform="antsRegistrationSyN[s,2]")
    # reg = ants.registration(fixed=fixed_image, moving=atlas, type_of_transform="SyN") # Faster Registartion for testing only
            
    transformed_patient = reg['warpedmovout']
    transform_paths = reg['fwdtransforms']

    return transformed_patient, transform_paths


def transform_scalar_img(fixed_image, atlas_modality, fwd_transform_paths, discrete=True):
    if discrete:
        interp = "nearestNeighbor"
    else: 
        interp = ""

    transformed_image = ants.apply_transforms(fixed=fixed_image,   
                                            moving=atlas_modality, 
                                            transformlist=fwd_transform_paths,
                                            interpolator=interp)

    return transformed_image

def reorient_tensor_wrapper(transformed_dti, warp_path):
    try:
        with tempfile.NamedTemporaryFile(suffix='.nii.gz') as transformed_dti_file, \
            tempfile.NamedTemporaryFile(suffix='.nii.gz') as transformed_rotated_dti_file:
            transformed_dti_path = transformed_dti_file.name
            transformed_rotated_dti_path = transformed_rotated_dti_file.name

            # print(transformed_dti_path)
            # Save input image
            ants.image_write(transformed_dti, transformed_dti_path)
            
            # Construct the ANTs command
            reorientTensor = f"ReorientTensorImage 3 {transformed_dti_path} {transformed_rotated_dti_path} {warp_path}"
    
            os.system(reorientTensor) 

            # Load and return the result
            rotated_tensor = ants.image_read(transformed_rotated_dti_path)
            
            return rotated_tensor
            
    except Exception as e:
        raise RuntimeError(f"Error processing image with ReorientTensorImage: {str(e)}")




def transform_tensor_img(fixed_image, dti_img, fwd_transform_paths):
    # Using ANTs registration throught the system
    warp_path = fwd_transform_paths[0]    
    
    # 1. Split into Six components
    dti_components = ants.split_channels(dti_img)
    #print(dti_components)

    # 2. Transform every component
    transformed_components = []
    for component in dti_components:
        transformed_component = ants.apply_transforms(fixed=fixed_image, 
                                                    moving=component, 
                                                    transformlist=fwd_transform_paths)
        transformed_components.append(transformed_component)
    transformed_dti_img = ants.merge_channels(transformed_components)

    # print(transformed_dti_img)
    
    # 3. Reorient Image ?!
    transformed_rotated_dti = reorient_tensor_wrapper(transformed_dti_img, warp_path)

    return transformed_rotated_dti

def reconstruct_pre_tumor_tissue(patient_scan, transform_DTI=False, transform_tissue_segementation=False, verbose=False):
    #====================================================================================================
    #
    # Reconstruction of the pre-infected tissue undelying the tumor using atlas Registration
    #
    # Inputs
    #   - patient_scan: MRI scan of patient with tumor as an ants_Images
    #   - transform_DTI: If true the atlas fiber tracts are also transformed in to the patients anatomy
    #   - transform_tissue_segementation: If true the atlas tissue segmentation 
    #                                       and probability maps for the tissue types are transformed in to the patients anatomy 
    #   - verbose: .... 
    #
    # Output
    #   - dict of the results containing the following
    #     Always:
    #       "T1" -> The Transformed T1 atlas (The generated reconstructed )
    #       "Transformation" -> Path to the Transformations created during the registration (Affine and Warp)
    #     When transform_DTI was set to true:
    #       - "fiber_tracts_FA" -> A scalar image of the patients fiber tracts
    #       - "fiber_tracts_tensor" -> A tensor image of the patients fiber tractations
    #     When transform_tissue_segmentation was set to true.
    #       - "TS" -> The tissue segmenation into WM, GM and CSF
    #       - "WM" -> The probability map for WM 
    #       - "GM" -> The probability map for GM
    #       - "CSF" -> The probability map fpr CSF 
    #
    #====================================================================================================
    if verbose:
        print("To be or not to be ~Shakespear")

    #if not ants.image_physical_space_consistency(patient_scan, atlas_t1_img): 
    #    print("The patient scan is not in the right SRI space! Process canceled")
    #    return
    
    
    print("Registering the Atlas on to the patient scan. This can take 2 or 3 min")
    transformed_t1, transformation = register_atlas(patient_scan, atlas_t1_img)
    print("Finished registration.")
    
    results = {"t1": transformed_t1, "transformation": transformation}

    if transform_DTI:
        if verbose:
            print("transforming the Fiber Tractation images in to the patients Anatomy")

        results["fiber_tracts_FA"] = transform_scalar_img(patient_scan, atlas_fiber_tracts_FA, transformation)
        results["fiber_tracts_DTI"] = transform_tensor_img(patient_scan, atlas_fiber_tracts_DTI, transformation)

    if transform_tissue_segementation:
        if verbose:
            print("transforming the tissue segmentation and estimation to the patient anatomy")

        transformed_TS = transform_scalar_img(patient_scan, atlas_tissue_segmentation, transformation)
        transformed_WM = transform_scalar_img(patient_scan, atlas_wm_pMap, transformation)
        transformed_GM = transform_scalar_img(patient_scan, atlas_gm_pMap, transformation)
        transformed_CSF = transform_scalar_img(patient_scan, atlas_csf_pMap, transformation)

        results["TS"] = transformed_TS
        results["WM"] = transformed_WM
        results["GM"] = transformed_GM
        results["CSF"] = transformed_CSF

    

    return results


def save_results(res, output_folder):

    if "t1" in res:
        name = os.path.join(output_folder, "reconstructed_t1_img.nii.gz")
        ants.image_write(res["t1"], name)

    if "transformation" in res:
        transform = res["transformation"]

        warp = transform[0]
        affine = transform[1]

        new_warp_path = os.path.join(output_folder, "deformation-field.nii.gz")
        new_affine_path = os.path.join(output_folder, "affine_transform.mat")

        shutil.move(warp, new_warp_path)
        shutil.move(affine, new_affine_path)

    if "fiber_tracts_FA" in res:
        name = os.path.join(output_folder, "fiber_tracts_FA.nii.gz")
        ants.image_write(res["fiber_tracts_FA"], name)

    if "fiber_tracts_DTI" in res:
        name = os.path.join(output_folder, "fiber_tracts_DTI.nii.gz")
        ants.image_write(res["fiber_tracts_DTI"], name)

    if "TS" in res:
        name = os.path.join(output_folder, "tissue_segmentation.nii.gz")
        ants.image_write(res["TS"], name)

    if "TS" in res:
        name = os.path.join(output_folder, "tissue_segmentation.nii.gz")
        ants.image_write(res["TS"], name)

    if "WM" in res:
        name = os.path.join(output_folder, "probability_map_WM.nii.gz")
        ants.image_write(res["WM"], name)    
    
    if "GM" in res:
        name = os.path.join(output_folder, "probability_map_GM.nii.gz")
        ants.image_write(res["GM"], name)

    if "CSF" in res:
        name = os.path.join(output_folder, "probability_map_CSF.nii.gz")
        ants.image_write(res["CSF"], name)    