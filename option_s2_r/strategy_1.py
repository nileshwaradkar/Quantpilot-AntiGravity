def rsi_cross_over(current_data):
    for ind in range(len(current_data) - 1):
        if current_data[ind][7] < current_data[ind][8] and current_data[ind + 1][7] >= current_data[ind + 1][8]:
            return True
    return False


def strategy_1(current_data):
    if current_data[-1][1] < current_data[-1][4] and current_data[-1][1] <= current_data[-1][6] <= current_data[-1][4]:
        # if current_data[-2][7] < current_data[-2][8] and current_data[-1][7] >= current_data[-1][8]:
        if rsi_cross_over(current_data):
            if current_data[-2][11] <= current_data[-1][11] and current_data[-1][11] > 0:
                # print(epoch_to_time(current_data[-1][0]))
                return True

    return False


def rsi_cross_over_opp(current_data):
    for ind in range(len(current_data) - 1):
        if current_data[ind][7] > current_data[ind][8] and current_data[ind + 1][7] <= current_data[ind + 1][8]:
            return True
    return False


def strategy_1_opp(current_data):
    if current_data[-1][1] > current_data[-1][4] and current_data[-1][1] >= current_data[-1][6] >= current_data[-1][4]:
        if rsi_cross_over_opp(current_data):
            if current_data[-2][11] >= current_data[-1][11] and current_data[-1][11] < 0:
                return True
    return False
