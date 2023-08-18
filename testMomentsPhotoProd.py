#!/usr/bin/env python3

# equation numbers refer to https://halldweb.jlab.org/doc-private/DocDB/ShowDocument?docid=6124&version=3

import ctypes
import functools
import math
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from scipy import stats
from typing import Any, Dict, List, Optional, Tuple

import py3nj

import ROOT

from testBasisFunc import enableRootACLiCOpenMp
enableRootACLiCOpenMp()


# always flush print() to reduce garbling of log files due to buffering
print = functools.partial(print, flush = True)


# C++ implementation of (complex conjugated) Wigner D function and spherical harmonics
# also provides complexT typedef for std::complex<double>
ROOT.gROOT.LoadMacro("./wignerD.C++")


# see https://root-forum.cern.ch/t/tf1-eval-as-a-function-in-rdataframe/50699/3
def declareInCpp(**kwargs: Any) -> None:
  '''Creates C++ variables (names = keys of kwargs) for PyROOT objects (values of kwargs) in PyVars:: namespace'''
  for key, value in kwargs.items():
    ROOT.gInterpreter.Declare(
f'''
namespace PyVars
{{
  auto& {key} = *reinterpret_cast<{type(value).__cpp_name__}*>({ROOT.addressof(value)});
}}
''')


# set of all possible waves up to ell = 2
PROD_AMPS: Dict[int, Dict[Tuple[int, int,], complex]] = {
  # negative-reflectivity waves
  -1 : {
    #J   M    amplitude
    (0,  0) :  1   + 0j,    # S_0^-
    (1, -1) : -0.4 + 0.1j,  # P_-1^-
    (1,  0) :  0.3 - 0.8j,  # P_0^-
    (1, +1) : -0.8 + 0.7j,  # P_+1^-
    (2, -2) :  0.1 - 0.4j,  # D_-2^-
    (2, -1) :  0.5 + 0.2j,  # D_-1^-
    (2,  0) : -0.1 - 0.2j,  # D_ 0^-
    (2, +1) :  0.2 - 0.1j,  # D_+1^-
    (2, +2) : -0.2 + 0.3j,  # D_+2^-
  },
  # positive-reflectivity waves
  +1 : {
    #J   M    amplitude
    (0,  0) :  0.5 + 0j,    # S_0^+
    (1, -1) :  0.5 - 0.1j,  # P_-1^+
    (1,  0) : -0.8 - 0.3j,  # P_0^+
    (1, +1) :  0.6 + 0.3j,  # P_+1^+
    (2, -2) :  0.2 + 0.1j,  # D_-2^+
    (2, -1) :  0.2 - 0.3j,  # D_-1^+
    (2,  0) :  0.1 - 0.2j,  # D_ 0^+
    (2, +1) :  0.2 + 0.5j,  # D_+1^+
    (2, +2) : -0.3 - 0.1j,  # D_+2^+
  },
}


def drawIntensityTF3(
  fcn:      ROOT.TF3,
  histName: str,
  nmbBins:  int = 25,
) -> None:
  '''Draws given TF3 for intensity distribution'''
  canv = ROOT.TCanvas()
  fcnHist = ROOT.TH3F(histName, ";cos#theta;#phi [deg];#Phi [deg]", nmbBins, -1, +1, nmbBins, -180, +180, nmbBins, -180, +180)
  xAxis = fcnHist.GetXaxis()
  yAxis = fcnHist.GetYaxis()
  zAxis = fcnHist.GetZaxis()
  for xBin in range(1, nmbBins + 1):
    for yBin in range(1, nmbBins + 1):
      for zBin in range(1, nmbBins + 1):
        x = xAxis.GetBinCenter(xBin)
        y = yAxis.GetBinCenter(yBin)
        z = zAxis.GetBinCenter(zBin)
        fcnHist.SetBinContent(xBin, yBin, zBin, fcn.Eval(x, y, z))
  fcnHist.SetMinimum(0)
  fcnHist.GetXaxis().SetTitleOffset(1.5)
  fcnHist.GetYaxis().SetTitleOffset(2)
  fcnHist.GetZaxis().SetTitleOffset(1.5)
  fcnHist.Draw("BOX2")
  canv.SaveAs(f"{fcnHist.GetName()}.pdf")


def plotComplexMatrix(
  matrix:         npt.NDArray[np.complex128],
  fileNamePrefix: str,
) -> None:
  plt.figure().colorbar(plt.matshow(np.real(matrix)))
  plt.savefig(f"{fileNamePrefix}_real.pdf")
  plt.close()
  plt.figure().colorbar(plt.matshow(np.imag(matrix)))
  plt.savefig(f"{fileNamePrefix}_imag.pdf")
  plt.close()
  plt.figure().colorbar(plt.matshow(np.absolute(matrix)))
  plt.savefig(f"{fileNamePrefix}_abs.pdf")
  plt.close()
  plt.figure().colorbar(plt.matshow(np.angle(matrix)))
  plt.savefig(f"{fileNamePrefix}_arg.pdf")
  plt.close()


def getMaxSpin(prodAmps: Dict[int, Dict[Tuple[int, int,], complex]]) -> int:
  '''Gets maximum spin from set of production amplitudes'''
  maxSpin = 0
  for refl in (-1, +1):
    for wave in prodAmps[refl]:
      ell = wave[0]
      maxSpin = ell if ell > maxSpin else maxSpin
  return maxSpin


def calcSpinDensElemSetFromWaves(
  refl:         int,      # reflectivity
  m1:           int,      # m
  m2:           int,      # m'
  prodAmp1:     complex,  # [ell]_m^refl
  prodAmp1NegM: complex,  # [ell]_{-m}^refl
  prodAmp2:     complex,  # [ell']_m'^refl
  prodAmp2NegM: complex,  # [ell']_{-m'}^refl
) -> Tuple[complex, complex, complex]:
  '''Calculates element of spin-density matrix components from given partial-wave amplitudes assuming rank 1'''
  rhos: List[complex] = 3 * [0 + 0j]
  rhos[0] +=                    (           prodAmp1     * prodAmp2.conjugate() + (-1)**(m1 - m2) * prodAmp1NegM * prodAmp2NegM.conjugate())  # Eq. (150)
  rhos[1] +=            -refl * ((-1)**m1 * prodAmp1NegM * prodAmp2.conjugate() + (-1)**m2        * prodAmp1     * prodAmp2NegM.conjugate())  # Eq. (151)
  rhos[2] += -(0 + 1j) * refl * ((-1)**m1 * prodAmp1NegM * prodAmp2.conjugate() - (-1)**m2        * prodAmp1     * prodAmp2NegM.conjugate())  # Eq. (152)
  return tuple(rhos)


def calcMomentSetFromWaves(
  prodAmps: Dict[int, Dict[Tuple[int, int,], complex]],
  L:        int,
  M:        int,
) -> Tuple[complex, complex, complex]:
  '''Calculates values of (H_0, H_1, H_2) with L and M from given production amplitudes assuming rank 1'''
  # Eqs. (154) to (156) assuming that rank is 1
  moments: List[complex] = 3 * [0 + 0j]
  for refl in (-1, +1):
    for wave1 in prodAmps[refl]:
      ell1:         int     = wave1[0]
      m1:           int     = wave1[1]
      prodAmp1:     complex = prodAmps[refl][wave1]
      prodAmp1NegM: complex = prodAmps[refl][(ell1, -m1)]
      for wave2 in prodAmps[refl]:
        ell2:         int     = wave2[0]
        m2:           int     = wave2[1]
        prodAmp2:     complex = prodAmps[refl][wave2]
        prodAmp2NegM: complex = prodAmps[refl][(ell2, -m2)]
        term = math.sqrt((2 * ell2 + 1) / (2 * ell1 + 1)) * (
            py3nj.clebsch_gordan(2 * ell2, 2 * L, 2 * ell1, 0,      0,     0,      ignore_invalid = True)  # (ell_2 0,    L 0 | ell_1 0  )
          * py3nj.clebsch_gordan(2 * ell2, 2 * L, 2 * ell1, 2 * m2, 2 * M, 2 * m1, ignore_invalid = True)  # (ell_2 m_2,  L M | ell_1 m_1)
        )
        if term == 0:  # invalid Clebsch-Gordan
          continue
        rhos: Tuple[complex, complex, complex] = calcSpinDensElemSetFromWaves(refl, m1, m2, prodAmp1, prodAmp1NegM, prodAmp2, prodAmp2NegM)
        moments[0] +=  term * rhos[0]  # H_0; Eq. (124)
        moments[1] += -term * rhos[1]  # H_1; Eq. (125)
        moments[2] += -term * rhos[2]  # H_2; Eq. (125)
  return tuple(moments)


def calcAllMomentsFromWaves(prodAmps: Dict[int, Dict[Tuple[int, int,], complex]]) -> List[Tuple[complex, complex, complex]]:
  '''Calculates moments for given production amplitudes assuming rank 1; the H_2(L, 0) are omitted'''
  moments: List[Tuple[complex, complex, complex]] = []
  maxSpin = getMaxSpin(prodAmps)
  norm = 1
  index = 0
  for L in range(2 * maxSpin + 2):  # calculate moments 2 units above maximum L (should be zero)
    for M in range(L + 1):          # calculate moments 1 unit above maximum M (should be zero)
      momentSet: List[complex] = list(calcMomentSetFromWaves(prodAmps, L, M))
      if ((abs(momentSet[0].imag) > 1e-15) or (abs(momentSet[1].imag) > 1e-15) or (abs(momentSet[2].real) > 1e-15)):
        print(f"Warning: expect (Im[H_0({L} {M})], Im[H_1({L} {M})], Re[H_2({L} {M})]) = (0, 0, 0)  found ({momentSet[0].imag}, {momentSet[1].imag}, {momentSet[2].imag})")
      else:
        # set respective real and imaginary parts exactly to zero.
        momentSet[0] = momentSet[0].real + 0j
        momentSet[1] = momentSet[1].real + 0j
        momentSet[2] = 0 + momentSet[2].imag * 1j
      if (M == 0 and momentSet[2] != 0):
        print(f"Warning: expect H_2({L} {M}) = 0  found {momentSet[2].imag}")
      # normalize to H_0(0, 0)
      norm = momentSet[0] if index == 0 else norm
      moments.append(tuple(moment / norm for moment in momentSet[:2 if M == 0 else 3]))
      index += 1
  index = 0
  for L in range(2 * maxSpin + 2):
    for M in range(L + 1):
      print(f"(H_0({L} {M}), H_1({L} {M})" + ("" if M == 0 else f", H_2({L} {M}))") + f" = {moments[index]}")
      index += 1
  return moments


def genDataFromWaves(
  nmbEvents:         int,                                         # number of events to generate
  polarization:      float,                                       # photon-beam polarization
  prodAmps:          Dict[int, Dict[Tuple[int, int,], complex]],  # partial-wave amplitudes
  efficiencyFormula: Optional[str] = None,                        # detection efficiency used to generate data
) -> ROOT.RDataFrame:
  '''Generates data according to set of partial-wave amplitudes (assuming rank 1) and given detection efficiency'''
  # construct efficiency function
  efficiencyFcn = ROOT.TF3("efficiencyGen", efficiencyFormula if efficiencyFormula else "1", -1, +1, -180, +180, -180, +180)
  efficiencyFcn.SetTitle(";cos#theta;#phi [deg];#Phi [deg]")
  efficiencyFcn.SetNpx(100)  # used in numeric integration performed by GetRandom()
  efficiencyFcn.SetNpy(100)
  efficiencyFcn.SetNpz(100)
  efficiencyFcn.SetMinimum(0)
  # draw efficiency function
  drawIntensityTF3(efficiencyFcn, histName = "hEfficiencyGen")

  # construct TF3 for intensity distribution in Eq. (153)
  # x = cos(theta) in [-1, +1], y = phi in [-180, +180] deg, z = Phi in [-180, +180] deg
  intensityComponentTerms: List[Tuple[str, str, str]] = []  # terms in sum of each intensity component
  for refl in (-1, +1):
    for wave1 in prodAmps[refl]:
      ell1:         int     = wave1[0]
      m1:           int     = wave1[1]
      prodAmp1:     complex = prodAmps[refl][wave1]
      prodAmp1NegM: complex = prodAmps[refl][(ell1, -m1)]
      decayAmp1 = f"Ylm({ell1}, {m1}, std::acos(x), TMath::DegToRad() * y)"
      for wave2 in prodAmps[refl]:
        ell2:         int     = wave2[0]
        m2:           int     = wave2[1]
        prodAmp2:     complex = prodAmps[refl][wave2]
        prodAmp2NegM: complex = prodAmps[refl][(ell2, -m2)]
        decayAmp2 = f"Ylm({ell2}, {m2}, std::acos(x), TMath::DegToRad() * y)"
        rhos: Tuple[complex, complex, complex] = calcSpinDensElemSetFromWaves(refl, m1, m2, prodAmp1, prodAmp1NegM, prodAmp2, prodAmp2NegM)
        terms = tuple(f"{decayAmp1} * complexT({rho.real}, {rho.imag}) * std::conj({decayAmp2})" for rho in rhos)  # Eq. (153)
        intensityComponentTerms.append(terms)
  # sum terms for each intensity component
  intensityComponentsFormula = []
  for iComponent in range(3):
    intensityComponentsFormula.append(f"({' + '.join([term[iComponent] for term in intensityComponentTerms])})")
  # sum intensity components
  intensityFormula = (
    f"std::real({intensityComponentsFormula[0]} "
    f"- {intensityComponentsFormula[1]} * {polarization} * std::cos(2 * TMath::DegToRad() * z) "
    f"- {intensityComponentsFormula[2]} * {polarization} * std::sin(2 * TMath::DegToRad() * z))"
    + (f" * ({efficiencyFormula})" if efficiencyFormula else ""))  # Eq. (163)
  print(f"intensity = {intensityFormula}")
  intensityFcn = ROOT.TF3("intensity", intensityFormula, -1, +1, -180, +180, -180, +180)
  intensityFcn.SetTitle(";cos#theta;#phi [deg];#Phi [deg]")
  intensityFcn.SetNpx(100)  # used in numeric integration performed by GetRandom()
  intensityFcn.SetNpy(100)
  intensityFcn.SetNpz(100)
  intensityFcn.SetMinimum(0)

  # draw intensity function
  #   intensityFcn.Draw("BOX2") does not work
  #   draw function "by hand" instead
  drawIntensityTF3(intensityFcn, histName = "hIntensity")

  # generate random data that follow intensity given by partial-wave amplitudes
  treeName = "data"
  fileName = f"{intensityFcn.GetName()}.root"
  df = ROOT.RDataFrame(nmbEvents)
  declareInCpp(intensityFcn = intensityFcn)  # use Python object in C++
  df.Define("point",    "double cosTheta, phiDeg, PhiDeg; PyVars::intensityFcn.GetRandom3(cosTheta, phiDeg, PhiDeg); std::vector<double> point = {cosTheta, phiDeg, PhiDeg}; return point;") \
    .Define("cosTheta", "point[0]") \
    .Define("theta",    "std::acos(cosTheta)") \
    .Define("phiDeg",   "point[1]") \
    .Define("phi",      "TMath::DegToRad() * phiDeg") \
    .Define("PhiDeg",   "point[2]") \
    .Define("Phi",      "TMath::DegToRad() * PhiDeg") \
    .Filter('if (rdfentry_ == 0) { cout << "Running event loop in genDataFromWaves()" << endl; } return true;') \
    .Snapshot(treeName, fileName, ROOT.std.vector[ROOT.std.string](["cosTheta", "theta", "phiDeg", "phi", "PhiDeg", "Phi"]))
    # snapshot is needed or else the `point` column would be regenerated for every triggered loop
    # noop filter before snapshot logs when event loop is running
    # !Note! for some reason, this is very slow
  return ROOT.RDataFrame(treeName, fileName)


def genAccepted2BodyPsPhotoProd(
  nmbEvents:         int,                   # number of events to generate
  efficiencyFormula: Optional[str] = None,  # detection efficiency used for acceptance correction
) -> ROOT.RDataFrame:
  '''Generates RDataFrame with two-body phase-space distribution weighted by given detection efficiency'''
  # construct efficiency function
  efficiencyFcn = ROOT.TF3("efficiencyReco", efficiencyFormula if efficiencyFormula else "1", -1, +1, -180, +180, -180, +180)
  efficiencyFcn.SetTitle(";cos#theta;#phi [deg];#Phi [deg]")
  efficiencyFcn.SetNpx(100)  # used in numeric integration performed by GetRandom()
  efficiencyFcn.SetNpy(100)
  efficiencyFcn.SetNpz(100)
  efficiencyFcn.SetMinimum(0)
  # draw efficiency function
  drawIntensityTF3(efficiencyFcn, histName = "hEfficiencyReco")

  # generate isotropic distributions in cos theta, phi, and Phi and weight with efficiency function
  treeName = "data"
  fileName = f"{efficiencyFcn.GetName()}.root"
  df = ROOT.RDataFrame(nmbEvents)
  declareInCpp(efficiencyFcn = efficiencyFcn)
  df.Define("point",    "double cosTheta, phiDeg, PhiDeg; PyVars::efficiencyFcn.GetRandom3(cosTheta, phiDeg, PhiDeg); std::vector<double> point = {cosTheta, phiDeg, PhiDeg}; return point;") \
    .Define("cosTheta", "point[0]") \
    .Define("theta",    "std::acos(cosTheta)") \
    .Define("phiDeg",   "point[1]") \
    .Define("phi",      "TMath::DegToRad() * phiDeg") \
    .Define("PhiDeg",   "point[2]") \
    .Define("Phi",      "TMath::DegToRad() * PhiDeg") \
    .Filter('if (rdfentry_ == 0) { cout << "Running event loop in genData2BodyPSPhotoProd()" << endl; } return true;') \
    .Snapshot(treeName, fileName, ROOT.std.vector[ROOT.std.string](["theta", "phi", "Phi"]))
    # snapshot is needed or else the `point` column would be regenerated for every triggered loop
    # noop filter before snapshot logs when event loop is running
  return ROOT.RDataFrame(treeName, fileName)


def calcIntegralMatrix(
  phaseSpaceData: ROOT.RDataFrame,  # (accepted) phase space data
  nmbGenEvents:   int,              # number of generated events
  polarization:   float,            # photon-beam polarization
  maxL:           int,              # maximum orbital angular momentum
) -> Dict[Tuple[int, ...], complex]:
  '''Calculates integral matrix of spherical harmonics for from provided phase-space data'''
  # get phase-space data data as NumPy arrays
  thetaValues = phaseSpaceData.AsNumpy(columns = ["theta"])["theta"]
  phiValues   = phaseSpaceData.AsNumpy(columns = ["phi"]  )["phi"]
  PhiValues   = phaseSpaceData.AsNumpy(columns = ["Phi"]  )["Phi"]
  nmbEvents = len(thetaValues)
  assert thetaValues.shape == (nmbEvents,) and thetaValues.shape == phiValues.shape == PhiValues.shape, (
    f"Not all NumPy arrays with input data have shape ({nmbEvents},): thetaValues: {thetaValues.shape} vs. phiValues: {phiValues.shape} vs. phiValues: {PhiValues.shape}")
  # calculate basis-function values for physical and measured moments; Eqs. (175) and (176)
  fMeasValues: Dict[Tuple[int, int, int], npt.NDArray[np.complex128]] = {}
  fPhysValues: Dict[Tuple[int, int, int], npt.NDArray[np.complex128]] = {}
  for momentIndex in range(3):
    for L in range(2 * maxL + 2):
      for M in range(L + 1):
        if momentIndex == 2 and M == 0:
          continue  # H_2(L, 0) are always zero and would lead to a singular acceptance integral matrix
        fMeasValues[(momentIndex, L, M)] = np.asarray(ROOT.f_meas(momentIndex, L, M, thetaValues, phiValues, PhiValues, polarization))
        fPhysValues[(momentIndex, L, M)] = np.asarray(ROOT.f_phys(momentIndex, L, M, thetaValues, phiValues, PhiValues, polarization))
  # calculate integral-matrix elements; Eq. (178)
  I_acc: Dict[Tuple[int, ...], complex] = {}
  for indices_meas, f_meas in fMeasValues.items():
    for indices_phys, f_phys in fPhysValues.items():
      I_acc[indices_meas + indices_phys] = 8 * math.pi**2 / nmbGenEvents * np.dot(f_meas, f_phys)
  return I_acc


def calculatePhotoProdMoments(
  inData:         ROOT.RDataFrame,                                  # input data with angular distribution
  polarization:   float,                                            # photon-beam polarization
  maxL:           int,                                              # maximum spin of decaying object
  integralMatrix: Optional[Dict[Tuple[int, ...], complex]] = None,  # acceptance integral matrix
) -> Tuple[List[Tuple[Tuple[int, int, int], complex]], Dict[Tuple[int, int, int, int, int, int], Tuple[float, float, float]]]:  # moment values and covariances
  '''Calculates photoproduction moments and their covariances'''
  # get data as NumPy arrays
  thetaValues = inData.AsNumpy(columns = ["theta"])["theta"]
  phiValues   = inData.AsNumpy(columns = ["phi"]  )["phi"]
  PhiValues   = inData.AsNumpy(columns = ["Phi"]  )["Phi"]
  print(f"{type(thetaValues)}; {thetaValues.shape}; {thetaValues.dtype}; {thetaValues.dtype.type}")
  nmbEvents = len(thetaValues)
  assert thetaValues.shape == (nmbEvents,) and thetaValues.shape == phiValues.shape == PhiValues.shape, (
    f"Not all NumPy arrays with input data have shape ({nmbEvents},): thetaValues: {thetaValues.shape} vs. phiValues: {phiValues.shape} vs. phiValues: {PhiValues.shape}")
  # get number of moments (the poor-man's way)
  nmbMoments = 0
  for momentIndex in range(3):
    for L in range(2 * maxL + 2):
      for M in range(L + 1):
        if momentIndex == 2 and M == 0:
          continue  # H_2(L, 0) are always zero and would lead to a singular acceptance integral matrix
        nmbMoments += 1
  # calculate basis-function values and values of measured moments
  f_meas = np.zeros((nmbMoments, nmbEvents), dtype = np.complex128)
  H_meas = np.zeros((nmbMoments),            dtype = np.complex128)
  iMoment = 0
  for momentIndex in range(3):
    for L in range(2 * maxL + 2):
      for M in range(L + 1):
        if momentIndex == 2 and M == 0:
          continue  # H_2(L, 0) are always zero and would lead to a singular acceptance integral matrix
        fcnVals = np.asarray(ROOT.f_meas(momentIndex, L, M, thetaValues, phiValues, PhiValues, polarization))  # Eq. (176)  # type: ignore
        f_meas[iMoment, :] = fcnVals
        H_meas[iMoment] = 2 * math.pi * np.sum(fcnVals)  # Eq. (179)  # type: ignore[operator] # see https://stackoverflow.com/a/74634650
        iMoment += 1
  # calculate covariances; Eqs. (88), (180), and (181)
  V_meas_aug = (2 * math.pi)**2 * nmbEvents * np.cov(f_meas, np.conjugate(f_meas))  # augmented covariance matrix
  # print measured moments
  iMoment = 0
  for momentIndex in range(3):
    for L in range(2 * maxL + 2):
      for M in range(L + 1):
        if momentIndex == 2 and M == 0:
          continue  # H_2(L, 0) are always zero
        print(f"H^meas_{momentIndex}(L = {L}, M = {M}) = {H_meas[iMoment]}")
        iMoment += 1
  H_phys     = np.zeros((nmbMoments), dtype = np.complex128)
  V_phys_aug = np.zeros((2 * nmbMoments, 2 * nmbMoments), dtype = np.complex128)
  if integralMatrix is None:
    # ideal detector
    H_phys     = H_meas
    V_phys_aug = V_meas_aug
  else:
    # get acceptance integral matrix
    I_acc = np.zeros((nmbMoments, nmbMoments), dtype = np.complex128)
    iMoment_meas = 0
    for momentIndex_meas in range(3):
      for L_meas in range(2 * maxL + 2):
        for M_meas in range(L_meas + 1):
          if momentIndex_meas == 2 and M_meas == 0:
            continue  # H_2(L, 0) are always zero
          iMoment_phys = 0
          for momentIndex_phys in range(3):
            for L_phys in range(2 * maxL + 2):
              for M_phys in range(L_phys + 1):
                if momentIndex_phys == 2 and M_phys == 0:
                  continue  # H_2(L, 0) are always zero
                I_acc[iMoment_meas, iMoment_phys] = integralMatrix[(momentIndex_meas, L_meas, M_meas, momentIndex_phys, L_phys, M_phys)]
                iMoment_phys += 1
          iMoment_meas += 1
    print(f"Acceptance integral matrix = \n{np.array2string(I_acc, precision = 3, suppress_small = True, max_line_width = 150)}")
    eigenVals, eigenVecs = np.linalg.eig(I_acc)
    print(f"I_acc eigenvalues = {eigenVals}")
    # print(f"I_acc eigenvectors = {eigenVecs}")
    # print(f"I_acc determinant = {np.linalg.det(I_acc)}")
    # print(f"I_acc = \n{np.array2string(I_acc, precision = 3, suppress_small = True, max_line_width = 150)}")
    plotComplexMatrix(I_acc, fileNamePrefix = "I_acc")
    I_inv = np.linalg.inv(I_acc)
    # eigenVals, eigenVecs = np.linalg.eig(I_inv)
    # print(f"I^-1 eigenvalues = {eigenVals}")
    # print(f"I^-1 = \n{np.array2string(I_inv, precision = 3, suppress_small = True, max_line_width = 150)}")
    plotComplexMatrix(I_inv, fileNamePrefix = "I_inv")
    # calculate physical moments, i.e. correct for detection efficiency
    H_phys = I_inv @ H_meas  # Eq. (83)
    # perform linear uncertainty propagation
    J = I_inv  # Jacobian of efficiency correction; Eq. (101)
    J_conj = np.zeros((nmbMoments, nmbMoments), dtype = np.complex128)  # conjugate Jacobian; Eq. (101)
    J_aug = np.block([
      [J,                    J_conj],
      [np.conjugate(J_conj), np.conjugate(J)],
    ])  # augmented Jacobian; Eq. (98)
    V_phys_aug = J_aug @ (V_meas_aug @ np.asmatrix(J_aug).H)  #!Note! @ is left-associative; Eq. (85)
  # normalize such that H_0(0, 0) = 1
  norm = H_phys[0]
  H_phys /= norm
  V_phys_aug /= norm**2
  # calculate covariances of real and imaginary parts
  V_phys_Hermit = V_phys_aug[:nmbMoments, :nmbMoments]  # Hermitian covariance matrix; Eq. (88)
  V_phys_pseudo = V_phys_aug[:nmbMoments, nmbMoments:]  # pseudo-covariance matrix; Eq. (88)
  V_phys_ReRe = (np.real(V_phys_Hermit) + np.real(V_phys_pseudo)) / 2  # Eq. (91)
  V_phys_ImIm = (np.real(V_phys_Hermit) - np.real(V_phys_pseudo)) / 2  # Eq. (92)
  V_phys_ReIm = (np.imag(V_phys_pseudo) - np.imag(V_phys_Hermit)) / 2  # Eq. (93)
  # reformat output
  momentsPhys:    List[Tuple[Tuple[int, int, int], complex]] = []
  momentsPhysCov: Dict[Tuple[int, ...], Tuple[float, ...]]   = {}  # cov[(i, L, M, j, L', M')] = (cov[ReRe], cov[ImIm], cov[ReIm])
  iMoment_phys = 0
  for momentIndex_phys in range(3):
    for L_phys in range(2 * maxL + 2):
      for M_phys in range(L_phys + 1):
        if momentIndex_phys == 2 and M_phys == 0:
          continue  # H_2(L, 0) are always zero
        momentsPhys.append(((momentIndex_phys, L_phys, M_phys), H_phys[iMoment_phys]))
        iMoment_meas = 0
        for momentIndex_meas in range(3):
          for L_meas in range(2 * maxL + 2):
            for M_meas in range(L_meas + 1):
              if momentIndex_meas == 2 and M_meas == 0:
                continue  # H_2(L, 0) are always zero
              momentsPhysCov[(momentIndex_meas, L_meas, M_meas, momentIndex_phys, L_phys, M_phys)] = (
                (V_phys_ReRe[iMoment_meas, iMoment_phys],
                 V_phys_ImIm[iMoment_meas, iMoment_phys],
                 V_phys_ReIm[iMoment_meas, iMoment_phys]))
              iMoment_meas += 1
        iMoment_phys += 1
  #TODO encapsulate moment values and covariances in object that takes care of the index mapping
  return momentsPhys, momentsPhysCov


def plotComparison(
  measVals:           Tuple[Tuple[float, float, Tuple[int, int, int]], ...],
  inputVals:          Tuple[float, ...],
  realPart:           bool,
  useMomentSubscript: bool,
) -> None:
  momentIndex = measVals[0][2][0]
  if realPart:
    fileNameSuffix    = "Re"
    legendEntrySuffix = "Real Part"
  else:
    fileNameSuffix    = "Im"
    legendEntrySuffix = "Imag Part"

  # overlay measured and input values
  hStack = ROOT.THStack(f"hCompare_H{momentIndex if useMomentSubscript else ''}_{fileNameSuffix}", "")
  nmbBins = len(measVals)
  # create histogram with measured values
  labelSubscript = f"_{{{momentIndex}}}" if useMomentSubscript else ""
  hMeas = ROOT.TH1D(f"Measured #it{{H}}{labelSubscript} {legendEntrySuffix}", ";;Value", nmbBins, 0, nmbBins)
  for index, measVal in enumerate(measVals):
    hMeas.SetBinContent(index + 1, measVal[0])
    hMeas.SetBinError  (index + 1, 1e-100 if measVal[1] < 1e-100 else measVal[1])  # ensure that also points with zero uncertainty are drawn
    hMeas.GetXaxis().SetBinLabel(index + 1, f"#it{{H}}{labelSubscript}({measVal[2][1]}, {measVal[2][2]})")
  hMeas.SetLineColor(ROOT.kRed)
  hMeas.SetMarkerColor(ROOT.kRed)
  hMeas.SetMarkerStyle(ROOT.kFullCircle)
  hMeas.SetMarkerSize(0.75)
  hStack.Add(hMeas, "PEX0")
  # create histogram with input values
  hInput = ROOT.TH1D("Input Values", ";;Value", nmbBins, 0, nmbBins)
  for index, inputVal in enumerate(inputVals):
    hInput.SetBinContent(index + 1, inputVal)
    hInput.SetBinError  (index + 1, 1e-100)  # must not be zero, otherwise ROOT does not draw x error bars; sigh
  hInput.SetMarkerColor(ROOT.kBlue)
  hInput.SetLineColor(ROOT.kBlue)
  hInput.SetLineWidth(2)
  hStack.Add(hInput, "PE")
  canv = ROOT.TCanvas()
  hStack.Draw("NOSTACK")
  # adjust y-range
  ROOT.gPad.Update()
  actualYRange = ROOT.gPad.GetUymax() - ROOT.gPad.GetUymin()
  yRangeFraction = 0.1 * actualYRange
  hStack.SetMaximum(ROOT.gPad.GetUymax() + yRangeFraction)
  hStack.SetMinimum(ROOT.gPad.GetUymin() - yRangeFraction)
  # adjust style of automatic zero line
  hStack.GetHistogram().SetLineColor(ROOT.kBlack)
  hStack.GetHistogram().SetLineStyle(ROOT.kDashed)
  # hStack.GetHistogram().SetLineWidth(0)  # remove zero line; see https://root-forum.cern.ch/t/continuing-the-discussion-from-an-unwanted-horizontal-line-is-drawn-at-y-0/50877/1
  canv.BuildLegend(0.7, 0.75, 0.99, 0.99)
  canv.SaveAs(f"{hStack.GetName()}.pdf")

  # plot residuals
  residuals = tuple((measVal[0] - inputVals[index]) / measVal[1] if measVal[1] > 0 else 0 for index, measVal in enumerate(measVals))
  hResidual = ROOT.TH1D(f"hResiduals_H{momentIndex if useMomentSubscript else ''}_{fileNameSuffix}",
    f"Residuals #it{{H}}{labelSubscript} {legendEntrySuffix};;(measured - input) / #sigma_{{measured}}", nmbBins, 0, nmbBins)
  chi2 = sum(tuple(residual**2 for residual in residuals[1 if momentIndex == 0 else 0:]))  # exclude Re and Im of H_0(0, 0) from chi^2
  ndf  = len(residuals[1 if momentIndex == 0 else 0:])
  for index, residual in enumerate(residuals):
    hResidual.SetBinContent(index + 1, residual)
    hResidual.SetBinError  (index + 1, 1e-100)  # must not be zero, otherwise ROOT does not draw x error bars; sigh
    hResidual.GetXaxis().SetBinLabel(index + 1, hMeas.GetXaxis().GetBinLabel(index + 1))
  hResidual.SetMarkerColor(ROOT.kBlue)
  hResidual.SetLineColor(ROOT.kBlue)
  hResidual.SetLineWidth(2)
  hResidual.SetMinimum(-3)
  hResidual.SetMaximum(+3)
  canv = ROOT.TCanvas()
  hResidual.Draw("PE")
  # draw zero line
  xAxis = hResidual.GetXaxis()
  line = ROOT.TLine()
  line.SetLineStyle(ROOT.kDashed)
  line.DrawLine(xAxis.GetBinLowEdge(xAxis.GetFirst()), 0, xAxis.GetBinUpEdge(xAxis.GetLast()), 0)
  # shade 1 sigma region
  box = ROOT.TBox()
  box.SetFillColorAlpha(ROOT.kBlack, 0.15)
  box.DrawBox(xAxis.GetBinLowEdge(xAxis.GetFirst()), -1, xAxis.GetBinUpEdge(xAxis.GetLast()), +1)
  # draw chi^2 info
  label = ROOT.TLatex()
  label.SetNDC()
  label.SetTextAlign(ROOT.kHAlignLeft + ROOT.kVAlignBottom)
  label.DrawLatex(0.12, 0.9075, f"#it{{#chi}}^{{2}}/n.d.f. = {chi2:.2f}/{ndf}, prob = {stats.distributions.chi2.sf(chi2, ndf) * 100:.0f}%")
  canv.SaveAs(f"{hResidual.GetName()}.pdf")


def setupPlotStyle() -> None:
  #TODO remove dependency from external file or add file to repo
  ROOT.gROOT.LoadMacro("~/rootlogon.C")
  ROOT.gROOT.ForceStyle()
  ROOT.gStyle.SetCanvasDefW(600)
  ROOT.gStyle.SetCanvasDefH(600)
  ROOT.gStyle.SetPalette(ROOT.kBird)
  # ROOT.gStyle.SetPalette(ROOT.kViridis)
  ROOT.gStyle.SetLegendFillColor(ROOT.kWhite)
  ROOT.gStyle.SetLegendBorderSize(1)
  # ROOT.gStyle.SetOptStat("ni")  # show only name and integral
  # ROOT.gStyle.SetOptStat("i")  # show only integral
  ROOT.gStyle.SetOptStat("")
  ROOT.gStyle.SetStatFormat("8.8g")
  ROOT.gStyle.SetTitleColor(1, "X")  # fix that for some mysterious reason x-axis titles of 2D plots and graphs are white
  ROOT.gStyle.SetTitleOffset(1.35, "Y")


if __name__ == "__main__":
  ROOT.gROOT.SetBatch(True)
  ROOT.gRandom.SetSeed(1234567890)
  # ROOT.EnableImplicitMT(10)
  setupPlotStyle()
  ROOT.gBenchmark.Start("Total execution time")

  # get data
  nmbEvents = 1000000
  nmbMcEvents = 10000000
  polarization = 1.0
  # formulas for detection efficiency
  # x = cos(theta) in [-1, +1], y = phi in [-180, +180] deg, z = Phi in [-180, +180] deg
  # efficiencyFormulaGen = "1"  # acc_perfect
  # efficiencyFormulaGen = "(1.5 - x * x) * (1.5 - y * y / (180 * 180)) * (1.5 - z * z / (180 * 180)) / 1.5**3"  # acc_1; even in all variables
  # efficiencyFormulaGen = "(0.75 + 0.25 * x) * (0.75 - 0.25 * (y / 180)) * (0.75 + 0.25 * (z / 180))"  # acc_2; odd in all variables
  efficiencyFormulaGen = "(0.6 + 0.4 * x) * (0.6 - 0.4 * (y / 180)) * (0.6 + 0.4 * (z / 180))"  # acc_3; odd in all variables
  # detune efficiency used to correct acceptance w.r.t. the one used to generate the data
  # efficiencyFormulaReco = efficiencyFormulaGen
  # efficiencyFormulaReco = efficiencyFormulaGen + " - (0.35 + 0.15 * x) * (0.35 - 0.15 * (y / 180)) * (0.35 + 0.15 * (z / 180))"  # detune_odd; detune by odd terms
  efficiencyFormulaReco = efficiencyFormulaGen + " - 0.15 * (1.5 - x * x) * (1.5 - y * y / (180 * 180)) * (1.5 - z * z / (180 * 180)) / (1.5**3)"  # detune_even; detune by even terms

  # input from partial-wave amplitudes
  ROOT.gBenchmark.Start("Time to generate MC data from partial waves")
  inputMoments: List[Tuple[complex, complex, complex]] = calcAllMomentsFromWaves(PROD_AMPS)
  dataPwaModel = genDataFromWaves(nmbEvents, polarization, PROD_AMPS, efficiencyFormulaGen)
  ROOT.gBenchmark.Stop("Time to generate MC data from partial waves")

  # plot data
  canv = ROOT.TCanvas()
  nmbBins = 25
  hist = dataPwaModel.Histo3D(
    ROOT.RDF.TH3DModel("hData", ";cos#theta;#phi [deg];#Phi [deg]", nmbBins, -1, +1, nmbBins, -180, +180, nmbBins, -180, +180),
    "cosTheta", "phiDeg", "PhiDeg")
  hist.SetMinimum(0)
  hist.GetXaxis().SetTitleOffset(1.5)
  hist.GetYaxis().SetTitleOffset(2)
  hist.GetZaxis().SetTitleOffset(1.5)
  hist.Draw("BOX2")
  canv.SaveAs(f"{hist.GetName()}.pdf")

  # generate accepted phase-space data
  ROOT.gBenchmark.Start("Time to generate phase-space MC data")
  dataAcceptedPs = genAccepted2BodyPsPhotoProd(nmbMcEvents, efficiencyFormulaReco)
  ROOT.gBenchmark.Stop("Time to generate phase-space MC data")
  # calculate integral matrix
  nmbOpenMpThreads = ROOT.getNmbOpenMpThreads()
  ROOT.gBenchmark.Start(f"Time to calculate integral matrix using {nmbOpenMpThreads} OpenMP threads")
  integralMatrix = calcIntegralMatrix(dataAcceptedPs, nmbGenEvents = nmbMcEvents, polarization = polarization, maxL = getMaxSpin(PROD_AMPS))
  ROOT.gBenchmark.Stop(f"Time to calculate integral matrix using {nmbOpenMpThreads} OpenMP threads")
  # calculate and print moments of accepted phase-space data
  print("Moments of accepted phase-space data")
  ROOT.gBenchmark.Start(f"Time to calculate moments of phase-space MC data using {nmbOpenMpThreads} OpenMP threads")
  momentsPs, momentsPsCov = calculatePhotoProdMoments(dataAcceptedPs, polarization = polarization, maxL = getMaxSpin(PROD_AMPS), integralMatrix = integralMatrix)
  ROOT.gBenchmark.Stop(f"Time to calculate moments of phase-space MC data using {nmbOpenMpThreads} OpenMP threads")
  for momentPs in momentsPs:
    print(f"Re[H^phys_{momentPs[0][0]}(L = {momentPs[0][1]}, M = {momentPs[0][2]})] = {momentPs[1].real} +- {math.sqrt(momentsPsCov[(*momentPs[0], *momentPs[0])][0])}")  # diagonal element for ReRe
    print(f"Im[H^phys_{momentPs[0][0]}(L = {momentPs[0][1]}, M = {momentPs[0][2]})] = {momentPs[1].imag} +- {math.sqrt(momentsPsCov[(*momentPs[0], *momentPs[0])][1])}")  # diagonal element for ImIm

  # calculate moments
  print("Moments of data generated according to PWA model")
  ROOT.gBenchmark.Start(f"Time to calculate moments using {nmbOpenMpThreads} OpenMP threads")
  moments, momentsCov = calculatePhotoProdMoments(dataPwaModel, polarization = polarization, maxL = getMaxSpin(PROD_AMPS), integralMatrix = integralMatrix)
  ROOT.gBenchmark.Stop(f"Time to calculate moments using {nmbOpenMpThreads} OpenMP threads")
  # print moments
  for moment in moments:
    print(f"Re[H^phys_{moment[0][0]}(L = {moment[0][1]}, M = {moment[0][2]})] = {moment[1].real} +- {math.sqrt(momentsCov[(*moment[0], *moment[0])][0])}")  # diagonal element for ReRe
    print(f"Im[H^phys_{moment[0][0]}(L = {moment[0][1]}, M = {moment[0][2]})] = {moment[1].imag} +- {math.sqrt(momentsCov[(*moment[0], *moment[0])][1])}")  # diagonal element for ImIm

  # compare with input values
  for momentIndex in range(3):
    # Re[H_i]
    measVals  = tuple((moment[1].real, math.sqrt(momentsCov[(*moment[0], *moment[0])][0]), moment[0]) for moment in moments if moment[0][0] == momentIndex)
    inputVals = tuple(inputMoment[momentIndex].real for inputMoment in inputMoments if len(inputMoment) > momentIndex)
    plotComparison(measVals, inputVals, realPart = True, useMomentSubscript = True)
    # Im[H_i]
    measVals  = tuple((moment[1].imag, math.sqrt(momentsCov[(*moment[0], *moment[0])][1]), moment[0]) for moment in moments if moment[0][0] == momentIndex)
    inputVals = tuple(inputMoment[momentIndex].imag for inputMoment in inputMoments if len(inputMoment) > momentIndex)
    plotComparison(measVals, inputVals, realPart = False, useMomentSubscript = True)

  ROOT.gBenchmark.Stop("Total execution time")
  _ = ctypes.c_float(0.0)  # dummy argument required by ROOT; sigh # type: ignore
  ROOT.gBenchmark.Summary(_, _)
  print("!Note! the 'TOTAL' time above is wrong; ignore")
