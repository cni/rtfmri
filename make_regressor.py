import random

LENGTH = 300 # num TRS
INTERVAL = 9 # #TR duration of trial
RANDOM = True
ITI = 3 # max duration of the ITI, which will be labelled -1

trial_types = []
for i in range(40):
    trial_types.append(1)
    trial_types.append(2)

random.shuffle(trial_types)
trial_types = [0] + trial_types



if __name__=='__main__':
    if RANDOM:
        fiti   = open(str(INTERVAL)+'tr_rand_iti.1D', 'w')
        # flabel = open(str(INTERVAL)+'tr_rand_noiti.1D', 'w')
        # ftime  = open(str(INTERVAL)+'tr_rand.1D', 'w')
    else:
        #just make 0s and ones
        f = open(str(INTERVAL)+'tr_01alt.1D', 'w')
    x = 1
    for tt in trial_types:
        for i in range(10):
            fiti.write(str(tt)+'\n')
        for i in range(random.randint(1,4)):
            fiti.write('0\n')
    fiti.close()
