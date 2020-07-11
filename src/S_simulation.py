"""
                                SARKAS: 1.0

An open-source pure-python molecular dynamics (MD) code for simulating plasmas.

Developed by the research group of:
Professor Michael S. Murillo
murillom@msu.edu
Dept. of Computational Mathematics, Science, and Engineering,
Michigan State University
"""

# Python modules
import numpy as np
import time
import sys
# Progress bar
from tqdm import tqdm

# import Sarkas MD modules
from S_thermostat import Thermostat, calc_kin_temp, remove_drift
from S_integrator import Integrator, calc_pot_acc, calc_pot_acc_fmm
from S_particles import Particles
from S_verbose import Verbose
from S_params import Params
from S_checkpoint import Checkpoint
from S_postprocessing import RadialDistributionFunction
import argparse


def main(params):
    """
    Run a Molecular Dynamics simulation with the parameters given by the input YAML file.

    Paramaters
    ----------
    params : class
        Simulation parameters.
    """
    time0 = time.time()
    # For restart and pva backups.
    checkpoint = Checkpoint(params)
    checkpoint.save_pickle(params)

    verbose = Verbose(params)
    verbose.sim_setting_summary(params)  # simulation setting summary

    integrator = Integrator(params)
    thermostat = Thermostat(params)

    ptcls = Particles(params)
    ptcls.load(params)

    if params.Control.verbose:
        print('\nParticles initialized.')

    # Calculate initial kinetic energy and temperature
    if not params.Potential.method == "FMM":
        U_init = calc_pot_acc(ptcls, params)
    else:
        U_init = calc_pot_acc_fmm(ptcls, params)

    Ks, Tps = calc_kin_temp(ptcls.vel, ptcls.species_num, ptcls.species_mass, params.kB)
    Tot_Kin = Ks.sum()
    Temperature = ptcls.species_conc.transpose() @ Tps
    E_init = U_init + Tot_Kin

    remove_drift(ptcls.vel, ptcls.species_num, ptcls.species_mass)
    #
    time_init = time.time()
    verbose.time_stamp("Initialization", time_init - time0)
    #
    f_log = open(params.Control.log_file, 'a+')
    print("\nInitial State:", file=f_log)
    if params.Control.units == "cgs":
        print("T = {:2.6e} [K], E = {:2.6e} [erg], K = {:2.6e} [erg], U = {:2.6e} [erg]".format(Temperature,
                                                                                                E_init, Tot_Kin,
                                                                                                U_init), file=f_log)
    else:
        print("T = {:2.6e} [K], E = {:2.6e} [J], K = {:2.6e} [J], U = {:2.6e} [J]".format(Temperature,
                                                                                          E_init, Tot_Kin, U_init),
              file=f_log)
    f_log.close()
    ##############################################
    # Equilibration Phase
    ##############################################
    if not params.load_method == "restart":
        checkpoint.therm_dump(ptcls, Ks, Tps, U_init, 0)
        if params.Control.verbose:
            print("\n------------- Equilibration -------------")
        for it in tqdm(range(params.Control.Neq), disable=not params.Control.verbose):
            # Calculate the Potential energy and update particles' data
            U_therm = integrator.update(ptcls, params)
            if (it + 1) % params.Control.therm_dump_step == 0:
                Ks, Tps = calc_kin_temp(ptcls.vel, ptcls.species_num, ptcls.species_mass, params.kB)
                checkpoint.therm_dump(ptcls, Ks, Tps, U_therm, it + 1)
            # Thermostate
            thermostat.update(ptcls.vel, it)
        remove_drift(ptcls.vel, ptcls.species_num, ptcls.species_mass)
        # Save the current state
        Ks, Tps = calc_kin_temp(ptcls.vel, ptcls.species_num, ptcls.species_mass, params.kB)
        U_therm = U_init
        checkpoint.dump(ptcls, Ks, Tps, U_therm, 0)

    time_eq = time.time()
    verbose.time_stamp("Equilibration", time_eq - time_init)
    ##############################################
    # Magnetic Equilibration Phase
    ##############################################
    # Turn on magnetic field, if not on already, and thermalize
    if params.Magnetic.on and params.Magnetic.elec_therm:
        params.Integrator.type = params.Integrator.mag_type
        integrator = Integrator(params)

        if params.Control.verbose:
            print("\n------------- Magnetic Equilibration -------------")

        for it in tqdm(range(params.Magnetic.Neq_mag), disable=(not params.Control.verbose)):
            # Calculate the Potential energy and update particles' data
            U_therm = integrator.update(ptcls, params)
            # Thermostate
            thermostat.update(ptcls.vel, it)

        remove_drift(ptcls.vel, ptcls.species_num, ptcls.species_mass)
        # Save the current state
        Ks, Tps = calc_kin_temp(ptcls.vel, ptcls.species_num, ptcls.species_mass, params.kB)
        checkpoint.dump(ptcls, Ks, Tps, U_therm, 0)
        #
        time_mag = time.time()
        verbose.time_stamp("Magnetic Equilibration", time_mag - time_eq)
        time_eq = time_mag

    ##############################################
    # Prepare for Production Phase
    ##############################################

    # Open output files
    if params.load_method == "restart":
        it_start = params.load_restart_step
        if params.Control.writexyz:
            # Particles' positions, velocities, accelerations for OVITO
            f_xyz = open(params.Control.checkpoint_dir + "/" + "pva_" + params.Control.fname_app + ".xyz", "a+")
    else:
        it_start = 0
        # Restart the pbc counter

        ptcls.pbc_cntr.fill(0.0)
        # Create array for storing energy information
        if params.Control.writexyz:
            # Particles' positions, velocities, accelerations for OVITO
            f_xyz = open(params.Control.checkpoint_dir + "/" + "pva_" + params.Control.fname_app + ".xyz", "w+")

    pscale = 1.0 / params.aws
    vscale = 1.0 / (params.aws * params.wp)
    ascale = 1.0 / (params.aws * params.wp ** 2)

    # Update measurement flag for rdf
    params.Control.measure = True

    ##############################################
    # Production Phase
    ##############################################
    if params.Control.verbose:
        print("\n------------- Production -------------")
    time_eq = time.time()
    for it in tqdm(range(it_start, params.Control.Nsteps), disable=(not params.Control.verbose)):
        # Move the particles and calculate the potential
        U_prod = integrator.update(ptcls, params)
        if (it + 1) % params.Control.dump_step == 0:
            # Save particles' data for restart
            Ks, Tps = calc_kin_temp(ptcls.vel, ptcls.species_num, ptcls.species_mass, params.kB)
            checkpoint.dump(ptcls, Ks, Tps, U_prod, it + 1)
            # Write particles' data to XYZ file for OVITO Visualization
            if params.Control.writexyz:
                f_xyz.writelines("{0:d}\n".format(params.total_num_ptcls))
                f_xyz.writelines("name x y z vx vy vz ax ay az\n")
                np.savetxt(f_xyz,
                           np.c_[ptcls.species_name, ptcls.pos * pscale, ptcls.vel * vscale, ptcls.acc * ascale],
                           fmt="%s %.6e %.6e %.6e %.6e %.6e %.6e %.6e %.6e %.6e")
    # Save production time
    time_prod = time.time()
    verbose.time_stamp("Production", time_prod - time_eq)
    if params.Control.writexyz:
        f_xyz.close()
    ##############################################
    # Finalization Phase
    ##############################################
    rdf = RadialDistributionFunction(params)
    rdf.save(ptcls.rdf_hist)
    rdf.plot()

    # Print elapsed times to screen
    time_tot = time.time()
    verbose.time_stamp("Total", time_tot - time0)
    ##############################################
    # End of simulation
    ##############################################


if __name__ == '__main__':
    # Construct the argument parser
    ap = argparse.ArgumentParser()

    # Add the arguments to the parser
    ap.add_argument("-t", "--pre_run_testing", required=False, help="Pre Run Testing Flag")
    ap.add_argument("-i", "--input", required=True, help="YAML Input file")
    ap.add_argument("-d", "--job_dir", required=False, help="Job Directory")
    ap.add_argument("-j", "--job_id", required=False, help="Job ID")
    ap.add_argument("-s", "--randseed", required=False, help="Random Number Seed")
    args = vars(ap.parse_args())

    params = Params()
    params.setup(args)  # Read initial conditions and setup parameters

    if not args["randseed"] is None:
        params.load_rand_seed = int(args["randseed"])

    main(params)