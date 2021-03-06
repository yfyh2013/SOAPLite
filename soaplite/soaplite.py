### DEFINE ###
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import (bytes, str, open, super, range,
                      zip, round, input, int, pow, object)
from ctypes import *
import os, argparse, glob
import numpy as np
import soaplite.genBasis
import ase, ase.io
import os


def _format_ase2clusgeo(obj, all_atomtypes=[]):
    """ Takes an ase Atoms object and returns numpy arrays and integers
    which are read by the internal clusgeo. Apos is currently a flattened
    out numpy array
    """
    #atoms metadata
    totalAN = len(obj)
    if all_atomtypes:
        atomtype_set = set(all_atomtypes)
    else:
        atomtype_set = set(obj.get_atomic_numbers())
    num_atomtypes = len(atomtype_set)

    atomtype_lst = np.sort(list(atomtype_set))
    n_atoms_per_type_lst = []
    pos_lst = []
    for atomtype in atomtype_lst:
        condition = obj.get_atomic_numbers() == atomtype
        pos_onetype = obj.get_positions()[condition]
        n_onetype = pos_onetype.shape[0]

        # store data in lists
        pos_lst.append(pos_onetype)
        n_atoms_per_type_lst.append(n_onetype)

    typeNs = n_atoms_per_type_lst
    Ntypes = len(n_atoms_per_type_lst)
    atomtype_lst
    Apos = np.concatenate(pos_lst).ravel()
    return Apos, typeNs, Ntypes, atomtype_lst, totalAN


def _get_supercell(obj, rCut=5.0):
    rCutHard = rCut + 5; # Giving extra space for hard cutOff
    """ Takes atoms object (with a defined cell) and a radial cutoff.
    Returns a supercell centered around the original cell
    generously extended to contain all spheres with the given radial
    cutoff centered around the original atoms.
    """

    cell_vectors = obj.get_cell()
    a1, a2, a3 = cell_vectors[0], cell_vectors[1], cell_vectors[2]

    # vectors perpendicular to two cell vectors
    b1 = np.cross(a2, a3, axis=0)
    b2 = np.cross(a3, a1, axis=0)
    b3 = np.cross(a1, a2, axis=0)
    # projections onto perpendicular vectors
    p1 = np.dot(a1, b1) / np.dot(b1, b1) * b1
    p2 = np.dot(a2, b2) / np.dot(b2, b2) * b2
    p3 = np.dot(a3, b3) / np.dot(b3, b3) * b3
    xyz_arr = np.linalg.norm(np.array([p1,p2,p3]), axis = 1)
    cell_images = np.ceil(rCutHard/xyz_arr)
    nx = int(cell_images[0])
    ny = int(cell_images[1])
    nz = int(cell_images[2])
    suce = obj * (1 + 2*nx, 1+ 2*ny,1+2*nz)
    shift = obj.get_cell()

    shifted_suce = suce.copy()
    shifted_suce.translate(-shift[0]*nx -shift[1]*ny - shift[2]*nz)

    return shifted_suce

def get_soap_locals(obj, Hpos, alp, bet, rCut=5.0, NradBas=5, Lmax=5, crossOver=True, all_atomtypes=[]):
    rCutHard = rCut + 5;
    assert Lmax <= 9, "l cannot exceed 9. Lmax={}".format(Lmax)
    assert Lmax >= 0, "l cannot be negative.Lmax={}".format(Lmax)
    assert rCutHard < 20.0001 , "hard redius cuttof cannot be larger than 17 Angs. rCut={}".format(rCutHard)
    assert rCutHard > 1.999 , "hard redius cuttof cannot be lower than 1 Ang. rCut={}".format(rCutHard)
    assert NradBas >= 2 , "number of basis functions cannot be lower than 2. NradBas={}".format(NradBas)
    assert NradBas <= 13 , "number of basis functions cannot exceed 12. NradBas={}".format(NradBas)
    # get clusgeo internal format for c-code
    Apos, typeNs, py_Ntypes, atomtype_lst, totalAN = _format_ase2clusgeo(obj, all_atomtypes)
    assert  py_Ntypes<=6  , "Number of types cannot exceed 6 with this implementation. types={}".format(py_Ntypes)
    Hpos = np.array(Hpos)
    py_Hsize = Hpos.shape[0]

    # flatten arrays
    Hpos = Hpos.flatten()
    alp = alp.flatten()
    bet = bet.flatten()

    # convert int to c_int
    lMax = c_int(Lmax)
    Hsize = c_int(py_Hsize)
    Ntypes = c_int(py_Ntypes)
    totalAN = c_int(totalAN)
    rCutHard = c_double(rCutHard)
    Nsize = c_int(NradBas)
    #convert int array to c_int array
    typeNs = (c_int * len(typeNs))(*typeNs)

    # convert to c_double arrays
    # alphas
    alphas = (c_double * len(alp))(*alp.tolist())
    # betas
    betas = (c_double * len(bet))(*bet.tolist())
    #Apos
    axyz = (c_double * len(Apos))(*Apos.tolist())
    #Hpos
    hxyz = (c_double * len(Hpos))(*Hpos.tolist())

    ### START SOAP###
    #path_to_so = os.path.dirname(os.path.abspath(__file__))
    _PATH_TO_SOAPLITE_SO = os.path.dirname(os.path.abspath(__file__))
    _SOAPLITE_SOFILES = glob.glob( "".join([ _PATH_TO_SOAPLITE_SO, "/../lib/libsoapP*.*so"]) )
    #print(_SOAPLITE_SOFILES)
    #print(len(_SOAPLITE_SOFILES))
    if(py_Ntypes==1) or not crossOver:
        substring = "lib/libsoapPy."
        libsoap = CDLL(next((s for s in _SOAPLITE_SOFILES if substring in s), None))
        libsoap.soap.argtypes = [POINTER (c_double),POINTER (c_double), POINTER (c_double),POINTER (c_double),
            POINTER (c_double), POINTER (c_int),c_double,c_int,c_int,c_int,c_int,c_int]
        libsoap.soap.restype = POINTER (c_double)
    elif(py_Ntypes==2):
        substring = "lib/libsoapPy2."
        libsoap2 = CDLL(next((s for s in _SOAPLITE_SOFILES if substring in s), None))
        libsoap2.soap.argtypes = [POINTER (c_double),POINTER (c_double), POINTER (c_double),POINTER (c_double),
            POINTER (c_double), POINTER (c_int),c_double,c_int,c_int,c_int,c_int,c_int]
        libsoap2.soap.restype = POINTER (c_double)
    elif(py_Ntypes==3):
        substring = "lib/libsoapPy3."
        libsoap3 = CDLL(next((s for s in _SOAPLITE_SOFILES if substring in s), None))
        libsoap3.soap.argtypes = [POINTER (c_double),POINTER (c_double), POINTER (c_double),POINTER (c_double),
            POINTER (c_double), POINTER (c_int),c_double,c_int,c_int,c_int,c_int,c_int]
        libsoap3.soap.restype = POINTER (c_double)
    elif(py_Ntypes==4):
        substring = "lib/libsoapPy4."
        libsoap4 = CDLL(next((s for s in _SOAPLITE_SOFILES if substring in s), None))
        libsoap4.soap.argtypes = [POINTER (c_double),POINTER (c_double), POINTER (c_double),POINTER (c_double),
            POINTER (c_double), POINTER (c_int),c_double,c_int,c_int,c_int,c_int,c_int]
        libsoap4.soap.restype = POINTER (c_double)
    elif(py_Ntypes==5):
        substring = "lib/libsoapPy5."
        libsoap5 = CDLL(next((s for s in _SOAPLITE_SOFILES if substring in s), None))
        libsoap5.soap.argtypes = [POINTER (c_double),POINTER (c_double), POINTER (c_double),POINTER (c_double),
            POINTER (c_double), POINTER (c_int),c_double,c_int,c_int,c_int,c_int,c_int]
        libsoap5.soap.restype = POINTER (c_double)
    elif(py_Ntypes==6):
        substring = "lib/libsoapPy6."
        libsoap6 = CDLL(next((s for s in _SOAPLITE_SOFILES if substring in s), None))
        libsoap6.soap.argtypes = [POINTER (c_double),POINTER (c_double), POINTER (c_double),POINTER (c_double),
            POINTER (c_double), POINTER (c_int),c_double,c_int,c_int,c_int,c_int,c_int]
        libsoap6.soap.restype = POINTER (c_double)
    # double* c, double* Apos,double* Hpos,int* typeNs,
    # int totalAN,int Ntypes,int Nsize, int l, int Hsize);
    if(crossOver):
        c = (c_double*(int((NradBas*(NradBas+1))/2)*(Lmax+1)*int((py_Ntypes*(py_Ntypes +1))/2)*py_Hsize))()
        if(py_Ntypes==1):
            c = libsoap.soap( c, axyz, hxyz, alphas, betas, typeNs, rCutHard, totalAN, Ntypes, Nsize, lMax, Hsize)
           
        elif(py_Ntypes==2):
            c = libsoap2.soap( c, axyz, hxyz, alphas, betas, typeNs, rCutHard, totalAN, Ntypes, Nsize, lMax, Hsize)
        elif(py_Ntypes==3):
            c = libsoap3.soap( c, axyz, hxyz, alphas, betas, typeNs, rCutHard, totalAN, Ntypes, Nsize, lMax, Hsize)
        elif(py_Ntypes==4):
            c = libsoap4.soap( c, axyz, hxyz, alphas, betas, typeNs, rCutHard, totalAN, Ntypes, Nsize, lMax, Hsize)
        elif(py_Ntypes==5):
            c = libsoap5.soap( c, axyz, hxyz, alphas, betas, typeNs, rCutHard, totalAN, Ntypes, Nsize, lMax, Hsize)
        elif(py_Ntypes==6):
            c = libsoap6.soap( c, axyz, hxyz, alphas, betas, typeNs, rCutHard, totalAN, Ntypes, Nsize, lMax, Hsize)
    else:
        c = (c_double*(int((NradBas*(NradBas+1))/2)*(Lmax+1)*py_Ntypes*py_Hsize))()
        c = libsoap.soap( c, axyz, hxyz, alphas, betas, typeNs, rCutHard, totalAN, Ntypes, Nsize, lMax, Hsize)
   
    #   return c;
    if(crossOver):
        crosTypes = int((py_Ntypes*(py_Ntypes+1))/2)
        return np.ctypeslib.as_array( c, shape=(py_Hsize,int((NradBas*(NradBas+1))/2)*(Lmax+1)*crosTypes))
    else:
        shape = (py_Hsize,int((NradBas*(NradBas+1))/2)*(Lmax+1)*py_Ntypes)
        return np.ctypeslib.as_array( c, shape=(py_Hsize,int((NradBas*(NradBas+1))/2)*(Lmax+1)*py_Ntypes))

def get_soap_structure(obj, alp, bet, rCut=5.0, NradBas=5, Lmax=5, crossOver=True, all_atomtypes=[]):
    Apos, typeNs, py_Ntypes, atomtype_lst, totalAN = _format_ase2clusgeo(obj, all_atomtypes)
    Hpos = Apos.copy().reshape((-1,3))
    arrsoap = get_soap_locals(obj, Hpos, alp, bet,  rCut, NradBas, Lmax, crossOver, all_atomtypes=all_atomtypes)
    return arrsoap

def get_periodic_soap_locals(obj, Hpos, alp, bet, rCut=5.0, NradBas=5, Lmax=5,crossOver=True, all_atomtypes=[]):
    # get supercells
    suce = _get_supercell(obj, rCut)

    arrsoap = get_soap_locals(suce, Hpos, alp, bet, rCut, NradBas=NradBas, Lmax=Lmax, crossOver=crossOver, all_atomtypes=all_atomtypes)

    return arrsoap

def get_periodic_soap_structure(obj, alp, bet, rCut=5.0, NradBas=5, Lmax=5, crossOver=True, all_atomtypes=[]):
    Apos, typeNs, py_Ntypes, atomtype_lst, totalAN = _format_ase2clusgeo(obj, all_atomtypes)
    Hpos = obj.get_positions().reshape((-1,3))
    suce = _get_supercell(obj, rCut)

    arrsoap = get_soap_locals(suce, Hpos, alp, bet, rCut, NradBas, Lmax, crossOver, all_atomtypes=all_atomtypes)
    return arrsoap
