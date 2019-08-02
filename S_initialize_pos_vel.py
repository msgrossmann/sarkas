import numpy as np
import S_global_names as glb
import S_constants as const
import sys

# Assigns velocities with Maxwell-Boltzmann (Gaussian) distribution and positions with uniform random distribution
#def initial(seed_int,N,Lv,pos,vel,T_desired):
def initial(T_desired,mpiComm):
    seed_int = glb.seed_int
    N = glb.N #mpiComm.Nl #CORRECT WAY!!!
    Lv = glb.Lv #mpiComm.Ll
    q1 = glb.q1
    q2 = glb.q2
    ai = glb.ai
    mi = const.pMass

    np.random.seed(123)

    pos = np.zeros((N, glb.d))
    vel = np.zeros_like(pos)


    #sig = np.sqrt(T_desired/3)      # standard deviation in terms of temperature in reduced units
    #print("sig = ", sig)
    #sig = np.sqrt(q1*q2/ai/mi/glb.Gamma)
    if(glb.potential_type == glb.Yukawa_PP or glb.potential_type == glb.Yukawa_P3M):
        if(glb.units == "cgs"):
            sig = np.sqrt(q1*q2/ai/mi/glb.Gamma)

        elif(glb.units == "mks"):
            sig = np.sqrt(q1*q2/ai/mi/glb.Gamma/(4*np.pi*const.eps_0))

        elif(glb.units == "Yukawa"):
            sig = np.sqrt(1./glb.Gamma/3)

    if(glb.potential_type == glb.EGS):
        if(glb.units == "cgs"):
          sig = np.sqrt(q1*q2/ai/mi/glb.T_desired)
        elif(glb.units == "mks"):
          sig = np.sqrt(q1*q2/ai/mi/glb.T_desired/(4*np.pi*const.eps_0))

    #Box-Muller transform to generate Gaussian random numbers from uniform random numbers
    u1 = np.random.random(N)
    u2 = np.random.random(N)
    u3 = np.random.random(N)
    u4 = np.random.random(N)

    vel[:,0] = sig*np.sqrt(-2*np.log(u1))*np.cos(2*np.pi*u2) #distribution of vx
    vel[:,1] = sig*np.sqrt(-2*np.log(u1))*np.sin(2*np.pi*u2) #distribution of vy
    vel[:,2] = sig*np.sqrt(-2*np.log(u3))*np.cos(2*np.pi*u4) #distribution of vz

    #computing the mean of each velocity component to impose mean value of the velocity components to be zero
    vx_mean = np.mean(vel[:,0])
    vy_mean = np.mean(vel[:,1])
    vz_mean = np.mean(vel[:,2])

    #mean value of the velocity components to be zero
    vel[:,0] = vel[:,0] - vx_mean
    vel[:,1] = vel[:,1] - vy_mean
    vel[:,2] = vel[:,2] - vz_mean
    
    # initializing with random positions (Correct way)
    #pos[:,0] = Lv[0]*np.random.random(N) + mpiComm.Lmin[0]
    #pos[:,1] = Lv[1]*np.random.random(N) + mpiComm.Lmin[1]
    #pos[:,2] = Lv[2]*np.random.random(N) + mpiComm.Lmin[2]

    pos[:,0] = Lv[0]*np.random.random(N)
    pos[:,1] = Lv[1]*np.random.random(N)
    pos[:,2] = Lv[2]*np.random.random(N)

    Lmax = mpiComm.Lmax
    Lmin = mpiComm.Lmin
    posX = pos[:,0]
    posY = pos[:,1]
    posZ = pos[:,2]
    filter_X = np.logical_and(posX < Lmax[0] , posX > Lmin[0] )
    filter_Y = np.logical_and(posY < Lmax[1] , posY > Lmin[1] )
    filter_Z = np.logical_and(posZ < Lmax[2] , posZ > Lmin[2] )
    filter_total = np.logical_and.reduce( (filter_X,filter_Y,filter_Z) )
    filter_index = np.where(filter_total)

    pos = pos[filter_index,:][0]
    vel = vel[filter_index,:][0]
    acc = np.zeros_like(pos)

    print("rank = %d, len(pos) = %d" %(mpiComm.rank,len(pos[:,0])))


    return pos, vel, acc